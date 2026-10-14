"""CSRF protection, rate limiting, role checks, security headers and small audit helpers."""
import hmac
import re
import secrets
import threading
import time
from collections import defaultdict, deque
from functools import wraps

from flask import abort, current_app, jsonify, request, session
from flask_login import current_user

from .extensions import db
from .models import ErrorLog, UsageEvent

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


# ---------------------------------------------------------------- CSRF
def csrf_token():
    if "_csrf" not in session:
        session["_csrf"] = secrets.token_urlsafe(32)
    return session["_csrf"]


def csrf_protect():
    if request.method in SAFE_METHODS:
        return
    sent = request.headers.get("X-CSRF-Token") or request.form.get("csrf_token") or ""
    expected = session.get("_csrf", "")
    if not expected or not hmac.compare_digest(sent, expected):
        if request.path.startswith("/api/") or request.is_json:
            resp = jsonify(error="Your session expired. Please refresh the page.")
            resp.status_code = 400
            abort(resp)
        abort(400, "Invalid or missing CSRF token. Refresh the page and try again.")


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


def rate_limit(bucket, config_key, window=60, methods=None):
    def deco(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            if methods and request.method not in methods:
                return fn(*args, **kwargs)
            limit = current_app.config.get(config_key, 30)
            who = f"u{current_user.id}" if current_user.is_authenticated else f"ip{client_ip()}"
            ok, retry = limiter.hit(f"{bucket}:{who}", limit, window)
            if not ok:
                msg = f"Too many requests. Please wait {retry}s and try again."
                if request.path.startswith("/api/"):
                    resp = jsonify(error=msg)
                    resp.status_code = 429
                    resp.headers["Retry-After"] = str(retry)
                    abort(resp)
                abort(429, msg)
            return fn(*args, **kwargs)
        return wrapper
    return deco


def client_ip():
    return request.remote_addr or "unknown"


# ---------------------------------------------------------------- Roles
def admin_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not current_user.is_authenticated:
            abort(401)
        if not current_user.is_admin:
            abort(403)
        return fn(*args, **kwargs)
    return wrapper


def api_login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not current_user.is_authenticated:
            return jsonify(error="Please sign in again."), 401
        return fn(*args, **kwargs)
    return wrapper


# ---------------------------------------------------------------- Headers
CSP = (
    "default-src 'self'; "
    "script-src 'self' https://cdn.jsdelivr.net; "
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://cdn.jsdelivr.net; "
    "font-src 'self' data: https://fonts.gstatic.com https://cdn.jsdelivr.net; "
    "img-src 'self' data: blob: https:; "
    "media-src 'self' blob:; "
    "connect-src 'self'; "
    "frame-ancestors 'none'; base-uri 'self'; form-action 'self' https://accounts.google.com"
)


def apply_security_headers(resp):
    resp.headers.setdefault("Content-Security-Policy", CSP)
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["X-Frame-Options"] = "DENY"
    resp.headers["Referrer-Policy"] = "same-origin"
    resp.headers["Permissions-Policy"] = "microphone=(self), camera=(), geolocation=()"
    if request.is_secure:
        resp.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return resp


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
        uid = user_id if user_id is not None else (current_user.id if current_user.is_authenticated else None)
        db.session.add(UsageEvent(user_id=uid, kind=kind, model=model, ok=ok))
        db.session.commit()
    except Exception:  # never break a request because of analytics
        db.session.rollback()


def log_error(source, message, user_id=None):
    try:
        uid = user_id
        if uid is None:
            try:
                uid = current_user.id if current_user.is_authenticated else None
            except Exception:
                uid = None
        db.session.add(ErrorLog(source=source[:80], message=str(message)[:4000], user_id=uid))
        db.session.commit()
    except Exception:
        db.session.rollback()
    current_app.logger.warning("[%s] %s", source, message)
