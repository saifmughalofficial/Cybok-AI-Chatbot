"""Rate limiting, validation and small audit helpers."""
import logging
import re
import threading
import time
from collections import defaultdict, deque

from .extensions import db
from .models import ErrorLog, UsageEvent

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
log = logging.getLogger("cybok")


# ---------------------------------------------------------------- Rate limiting
class RateLimiter:
    """In-memory sliding-window limiter. Good for a single process; swap for Redis when scaling out."""

    def __init__(self):
        self._hits = defaultdict(deque)
        self._lock = threading.Lock()

    def hit(self, key, limit, window):
        now = time.monotonic()
        with self._lock:
            q = self._hits[key]
            while q and now - q[0] > window:
                q.popleft()
            if len(q) >= limit:
                return False, int(window - (now - q[0])) + 1
            q.append(now)
            return True, 0


limiter = RateLimiter()


def rate_problem(bucket, user_id, limit, window=60):
    """None if allowed, otherwise a friendly message."""
    ok, retry = limiter.hit(f"{bucket}:u{user_id}", limit, window)
    return None if ok else f"Too many requests. Please wait {retry}s and try again."


# ---------------------------------------------------------------- Validation helpers
def clean_text(value, max_len, default=""):
    if value is None:
        return default
    value = str(value).replace("\x00", "").strip()
    return value[:max_len]


def valid_email(email):
    return bool(email) and len(email) <= 255 and bool(EMAIL_RE.match(email))


def password_problem(pw):
    if not pw or len(pw) < 8:
        return "Password must be at least 8 characters."
    if len(pw) > 200:
        return "Password is too long."
    if not re.search(r"[A-Za-z]", pw) or not re.search(r"\d", pw):
        return "Password must contain at least one letter and one number."
    return None


# ---------------------------------------------------------------- Audit
def log_usage(kind, model=None, ok=True, user_id=None):
    try:
        db.session.add(UsageEvent(user_id=user_id, kind=kind, model=model, ok=ok))
        db.session.commit()
    except Exception:  # never break a request because of analytics
        db.session.rollback()


def log_error(source, message, user_id=None):
    try:
        db.session.add(ErrorLog(source=source[:80], message=str(message)[:4000], user_id=user_id))
        db.session.commit()
    except Exception:
        db.session.rollback()
    log.warning("[%s] %s", source, message)
