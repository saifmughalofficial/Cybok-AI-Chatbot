"""Database models. Every user-owned row carries user_id and every query filters by it."""
import json
import secrets
import uuid
from datetime import datetime, timezone

from werkzeug.security import check_password_hash, generate_password_hash

from .extensions import db


def utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def new_id():
    return uuid.uuid4().hex


def iso(dt):
    return dt.replace(tzinfo=timezone.utc).isoformat() if dt else None


class User(db.Model):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(255), unique=True, index=True, nullable=False)
    password_hash = db.Column(db.String(255))
    google_id = db.Column(db.String(255), unique=True)
    avatar = db.Column(db.String(500))  # stored filename, or remote URL (Google)
    role = db.Column(db.String(20), default="user", nullable=False)
    disabled = db.Column(db.Boolean, default=False, nullable=False)
    session_version = db.Column(db.Integer, default=1, nullable=False)
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)
    last_seen_at = db.Column(db.DateTime, default=utcnow)

    settings = db.relationship("UserSettings", uselist=False, back_populates="user", cascade="all, delete-orphan")

    @property
    def is_active(self):
        return not self.disabled

    @property
    def is_admin(self):
        return self.role == "admin"

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return bool(self.password_hash) and check_password_hash(self.password_hash, password)

    @property
    def avatar_url(self):
        if not self.avatar:
            return None
        if self.avatar.startswith("http"):
            return self.avatar
        return f"/media/avatar/{self.id}?v={self.avatar[:8]}"

    @property
    def initials(self):
        parts = [p for p in (self.name or "?").split() if p]
        return ("".join(p[0] for p in parts[:2]) or "?").upper()

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "email": self.email,
            "avatar": self.avatar_url,
            "initials": self.initials,
            "role": self.role,
            "has_password": bool(self.password_hash),
            "google_linked": bool(self.google_id),
            "created_at": iso(self.created_at),
        }


class UserSettings(db.Model):
    __tablename__ = "user_settings"
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    theme = db.Column(db.String(10), default="system")
    accent = db.Column(db.String(20), default="cybok")
    default_model = db.Column(db.String(80))
    response_style = db.Column(db.String(20), default="balanced")  # concise | balanced | detailed
    custom_instructions = db.Column(db.Text, default="")
    enter_to_send = db.Column(db.Boolean, default=True)
    save_history = db.Column(db.Boolean, default=True)
    email_notifications = db.Column(db.Boolean, default=True)
    system_notifications = db.Column(db.Boolean, default=False)
    voice_autospeak = db.Column(db.Boolean, default=False)
    voice_name = db.Column(db.String(120), default="")
    voice_rate = db.Column(db.Float, default=1.0)
    font_size = db.Column(db.String(10), default="md")

    user = db.relationship("User", back_populates="settings")

    FIELDS = ["theme", "accent", "default_model", "response_style", "custom_instructions", "enter_to_send",
              "save_history", "email_notifications", "system_notifications", "voice_autospeak",
              "voice_name", "voice_rate", "font_size"]

    def to_dict(self):
        return {f: getattr(self, f) for f in self.FIELDS}


class Conversation(db.Model):
    __tablename__ = "conversations"
    id = db.Column(db.String(32), primary_key=True, default=new_id)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    title = db.Column(db.String(200), default="New chat", nullable=False)
    model = db.Column(db.String(80))
    pinned = db.Column(db.Boolean, default=False, index=True)
    archived = db.Column(db.Boolean, default=False, index=True)
    temporary = db.Column(db.Boolean, default=False)
    deleted_at = db.Column(db.DateTime, index=True)  # soft delete -> Trash
    share_token = db.Column(db.String(64), unique=True, index=True)
    share_enabled = db.Column(db.Boolean, default=False)
    shared_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=utcnow, index=True, nullable=False)

    messages = db.relationship("Message", backref="conversation", cascade="all, delete-orphan",
                               order_by="Message.id", lazy="dynamic")

    def ensure_share_token(self):
        if not self.share_token:
            self.share_token = secrets.token_urlsafe(24)
        return self.share_token

    def to_dict(self):
        return {
            "id": self.id,
            "title": self.title,
            "model": self.model,
            "pinned": self.pinned,
            "archived": self.archived,
            "temporary": self.temporary,
            "deleted": self.deleted_at is not None,
            "shared": bool(self.share_enabled and self.share_token),
            "share_url": f"/share/{self.share_token}" if self.share_enabled and self.share_token else None,
            "created_at": iso(self.created_at),
            "updated_at": iso(self.updated_at),
        }


class Message(db.Model):
    __tablename__ = "messages"
    id = db.Column(db.Integer, primary_key=True)
    conversation_id = db.Column(db.String(32), db.ForeignKey("conversations.id", ondelete="CASCADE"),
                                index=True, nullable=False)
    role = db.Column(db.String(16), nullable=False)  # user | assistant
    content = db.Column(db.Text, default="", nullable=False)
    model = db.Column(db.String(80))
    status = db.Column(db.String(16), default="done")  # done | streaming | stopped | error
    feedback = db.Column(db.Integer, default=0)  # 1 like, -1 dislike
    attachments = db.Column(db.Text, default="[]")  # JSON list of file ids
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)

    @property
    def attachment_ids(self):
        try:
            return json.loads(self.attachments or "[]")
        except ValueError:
            return []

    def to_dict(self, files=None):
        return {
            "id": self.id,
            "role": self.role,
            "content": self.content,
            "model": self.model,
            "status": self.status,
            "feedback": self.feedback,
            "attachments": files if files is not None else [],
            "created_at": iso(self.created_at),
        }


class File(db.Model):
    """Binary files: user uploads and generated images. Stored on disk under a random name."""
    __tablename__ = "files"
    id = db.Column(db.String(32), primary_key=True, default=new_id)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    name = db.Column(db.String(255), nullable=False)
    mime = db.Column(db.String(120))
    ext = db.Column(db.String(16))
    size = db.Column(db.Integer, default=0)
    storage_path = db.Column(db.String(500), nullable=False)  # relative to UPLOAD_DIR
    source = db.Column(db.String(16), default="upload")  # upload | generated
    kind = db.Column(db.String(16), default="document")  # document | image | data | code
    extracted_text = db.Column(db.Text)
    meta = db.Column(db.Text, default="{}")
    folder = db.Column(db.String(80), default="")
    in_library = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)

    @property
    def meta_dict(self):
        try:
            return json.loads(self.meta or "{}")
        except ValueError:
            return {}

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "mime": self.mime,
            "ext": self.ext,
            "size": self.size,
            "kind": self.kind,
            "source": self.source,
            "folder": self.folder or "",
            "url": f"/media/file/{self.id}",
            "download_url": f"/media/file/{self.id}?download=1",
            "has_text": bool(self.extracted_text),
            "meta": self.meta_dict,
            "created_at": iso(self.created_at),
        }


class GeneratedContent(db.Model):
    """AI-generated output: images, logos, and saved text responses."""
    __tablename__ = "generated_content"
    id = db.Column(db.String(32), primary_key=True, default=new_id)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    content_type = db.Column(db.String(16), nullable=False)  # image | logo | text
    title = db.Column(db.String(200))
    prompt = db.Column(db.Text)
    output = db.Column(db.Text)  # text output, or SVG source for vector logos
    file_id = db.Column(db.String(32), db.ForeignKey("files.id", ondelete="SET NULL"))
    style = db.Column(db.String(60))
    meta = db.Column(db.Text, default="{}")
    saved = db.Column(db.Boolean, default=False, index=True)  # visible in Library
    folder = db.Column(db.String(80), default="")
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)

    file = db.relationship("File")

    def to_dict(self):
        try:
            meta = json.loads(self.meta or "{}")
        except ValueError:
            meta = {}
        url = f"/media/file/{self.file_id}" if self.file_id else (
            f"/media/svg/{self.id}" if self.output and self.content_type == "logo" else None)
        return {
            "id": self.id,
            "content_type": self.content_type,
            "title": self.title,
            "prompt": self.prompt,
            "output": self.output if self.content_type == "text" else None,
            "url": url,
            "download_url": (url + ("&" if "?" in url else "?") + "download=1") if url else None,
            "style": self.style,
            "meta": meta,
            "saved": self.saved,
            "folder": self.folder or "",
            "created_at": iso(self.created_at),
        }


class AIModel(db.Model):
    """A chat model reachable through an OpenAI-compatible API. Add new ones from the admin panel."""
    __tablename__ = "ai_models"
    id = db.Column(db.Integer, primary_key=True)
    slug = db.Column(db.String(80), unique=True, nullable=False)
    name = db.Column(db.String(120), nullable=False)
    description = db.Column(db.String(300), default="")
    provider = db.Column(db.String(80), default="")  # display label e.g. "Groq"
    model_family = db.Column(db.String(120), default="")  # e.g. "Meta Llama 3.3 70B"
    api_base = db.Column(db.String(300), nullable=False)
    api_model = db.Column(db.String(200), nullable=False)
    api_key_env = db.Column(db.String(80), default="")
    api_key = db.Column(db.String(500), default="")  # optional; env var is preferred
    key_required = db.Column(db.Boolean, default=True)
    supports_vision = db.Column(db.Boolean, default=False)
    supports_streaming = db.Column(db.Boolean, default=True)
    temperature = db.Column(db.Float, default=0.7)
    max_tokens = db.Column(db.Integer, default=2048)
    context_chars = db.Column(db.Integer, default=24000)
    badge = db.Column(db.String(30), default="")
    enabled = db.Column(db.Boolean, default=True)
    sort_order = db.Column(db.Integer, default=100)


class AppSetting(db.Model):
    __tablename__ = "app_settings"
    key = db.Column(db.String(80), primary_key=True)
    value = db.Column(db.Text, default="")


class Announcement(db.Model):
    __tablename__ = "announcements"
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    body = db.Column(db.Text, default="")
    level = db.Column(db.String(16), default="info")  # info | success | warning
    active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=utcnow)

    def to_dict(self):
        return {"id": self.id, "title": self.title, "body": self.body, "level": self.level,
                "active": self.active, "created_at": iso(self.created_at)}


class UsageEvent(db.Model):
    __tablename__ = "usage_events"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, index=True)
    kind = db.Column(db.String(16), index=True)  # chat | image | logo | upload
    model = db.Column(db.String(120))
    ok = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=utcnow, index=True)


class ErrorLog(db.Model):
    __tablename__ = "error_logs"
    id = db.Column(db.Integer, primary_key=True)
    source = db.Column(db.String(80))
    message = db.Column(db.Text)
    user_id = db.Column(db.Integer)
    created_at = db.Column(db.DateTime, default=utcnow, index=True)

    def to_dict(self):
        return {"id": self.id, "source": self.source, "message": self.message,
                "user_id": self.user_id, "created_at": iso(self.created_at)}
