"""Central configuration. Every value can be overridden with an environment variable (see .env.example)."""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
INSTANCE_DIR = BASE_DIR / "instance"


def _bool(name, default=False):
    val = os.getenv(name)
    if val is None:
        return default
    return val.strip().lower() in {"1", "true", "yes", "on"}


def _int(name, default):
    try:
        return int(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


class Config:
    APP_NAME = "Cybok"
    TAGLINE = "Your AI. Your Workspace."
    CREATOR_NAME = "Saif Mughal"
    CREATOR_DESCRIPTION = "University Student • Faisalabad, Pakistan"
    VERSION = "1.0.0"

    SECRET_KEY = os.getenv("SECRET_KEY") or "dev-insecure-change-me"
    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL") or f"sqlite:///{(INSTANCE_DIR / 'cybok.db').as_posix()}"
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True}

    UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR") or (INSTANCE_DIR / "storage"))
    MAX_UPLOAD_MB = _int("MAX_UPLOAD_MB", 20)
    MAX_CONTENT_LENGTH = (MAX_UPLOAD_MB + 1) * 1024 * 1024

    # Official creation date of Cybok (YYYY-MM-DD). Seeds the database once;
    # afterwards it is managed from Admin > System. Leave empty if not decided.
    CYBOK_CREATION_DATE = os.getenv("CYBOK_CREATION_DATE", "").strip()

    # Cookies / sessions
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = _bool("SESSION_COOKIE_SECURE", False)
    REMEMBER_COOKIE_HTTPONLY = True
    REMEMBER_COOKIE_SAMESITE = "Lax"
    REMEMBER_COOKIE_SECURE = _bool("SESSION_COOKIE_SECURE", False)
    PERMANENT_SESSION_LIFETIME = 60 * 60 * 24 * 30

    # Public URL (used in password-reset emails and OAuth when behind a proxy)
    PUBLIC_URL = os.getenv("PUBLIC_URL", "").rstrip("/")
    BEHIND_PROXY = _bool("BEHIND_PROXY", False)

    # Google OAuth
    GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
    GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")

    # Email (SMTP) - optional. Without it, reset links are printed to the server console.
    MAIL_SERVER = os.getenv("MAIL_SERVER", "")
    MAIL_PORT = _int("MAIL_PORT", 587)
    MAIL_USERNAME = os.getenv("MAIL_USERNAME", "")
    MAIL_PASSWORD = os.getenv("MAIL_PASSWORD", "")
    MAIL_FROM = os.getenv("MAIL_FROM", "") or os.getenv("MAIL_USERNAME", "")
    MAIL_USE_TLS = _bool("MAIL_USE_TLS", True)

    # Comma-separated e-mails that automatically get the admin role
    ADMIN_EMAILS = [e.strip().lower() for e in os.getenv("ADMIN_EMAILS", "").split(",") if e.strip()]

    # Rate limits (requests per minute, per user)
    RATE_CHAT_PER_MIN = _int("RATE_CHAT_PER_MIN", 30)
    RATE_IMAGE_PER_MIN = _int("RATE_IMAGE_PER_MIN", 8)
    RATE_UPLOAD_PER_MIN = _int("RATE_UPLOAD_PER_MIN", 20)
    RATE_AUTH_PER_5MIN = _int("RATE_AUTH_PER_5MIN", 15)

    # Request timeout for AI providers (seconds)
    AI_TIMEOUT = _int("AI_TIMEOUT", 120)
