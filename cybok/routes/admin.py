"""Admin dashboard (role-based: only users with role == 'admin')."""
import os
from datetime import date, timedelta

from flask import Blueprint, current_app, jsonify, render_template, request
from flask_login import current_user, login_required
from sqlalchemy import func

from ..ai.chat import ProviderError, complete, is_available, resolve_key
from ..ai.images import PROVIDERS as IMAGE_PROVIDERS
from ..appsettings import all_settings, set_setting
from ..extensions import db
from ..files import storage_root
from ..models import (AIModel, Announcement, Conversation, ErrorLog, File, GeneratedContent, Message, UsageEvent,
                      User, iso, utcnow)
from ..security import admin_required, clean_text

bp = Blueprint("admin", __name__)


def body():
    return request.get_json(silent=True) or {}


@bp.route("/admin")
@login_required
@admin_required
def dashboard():
    return render_template("admin.html")


# ------------------------------------------------------------------ overview
@bp.get("/api/admin/stats")
@login_required
@admin_required
def stats():
    now = utcnow()
    day_ago, week_ago = now - timedelta(days=1), now - timedelta(days=7)
    count = lambda q: q.scalar() or 0
    usage = lambda kind, since=None: count(db.session.query(func.count(UsageEvent.id)).filter(
        UsageEvent.kind == kind, *( [UsageEvent.created_at >= since] if since else [])))
    storage_db = count(db.session.query(func.sum(File.size)))
    disk = 0
    try:
        for root, _, files in os.walk(storage_root()):
            disk += sum(os.path.getsize(os.path.join(root, f)) for f in files)
    except OSError:
        pass

    start = (now - timedelta(days=13)).date()
    series = {(start + timedelta(days=i)).isoformat(): {"chat": 0, "image": 0, "logo": 0, "upload": 0} for i in range(14)}
    rows = (db.session.query(func.date(UsageEvent.created_at), UsageEvent.kind, func.count(UsageEvent.id))
            .filter(UsageEvent.created_at >= start).group_by(func.date(UsageEvent.created_at), UsageEvent.kind).all())
    for d, kind, n in rows:
        key = d if isinstance(d, str) else d.isoformat()
        if key in series and kind in series[key]:
            series[key][kind] = n

    names = {m.slug: m.name for m in AIModel.query.all()}
    model_rows = (db.session.query(UsageEvent.model, func.count(UsageEvent.id))
                  .filter(UsageEvent.kind == "chat").group_by(UsageEvent.model)
                  .order_by(func.count(UsageEvent.id).desc()).limit(12).all())
    return jsonify(
        users=count(db.session.query(func.count(User.id))),
        users_new_week=count(db.session.query(func.count(User.id)).filter(User.created_at >= week_ago)),
        active_day=count(db.session.query(func.count(User.id)).filter(User.last_seen_at >= day_ago)),
        active_week=count(db.session.query(func.count(User.id)).filter(User.last_seen_at >= week_ago)),
        disabled=count(db.session.query(func.count(User.id)).filter(User.disabled.is_(True))),
        conversations=count(db.session.query(func.count(Conversation.id))),
        messages=count(db.session.query(func.count(Message.id))),
        ai_requests=usage("chat"), ai_requests_day=usage("chat", day_ago),
        ai_failures=count(db.session.query(func.count(UsageEvent.id)).filter(UsageEvent.kind == "chat", UsageEvent.ok.is_(False))),
        images=usage("image"), logos=usage("logo"), uploads=usage("upload"),
        generated_items=count(db.session.query(func.count(GeneratedContent.id))),
        files=count(db.session.query(func.count(File.id))),
        storage_bytes=max(storage_db, disk),
        errors_day=count(db.session.query(func.count(ErrorLog.id)).filter(ErrorLog.created_at >= day_ago)),
        series=[{"date": k, **v} for k, v in series.items()],
        model_usage=[{"model": names.get(m, m or "unknown"), "count": n} for m, n in model_rows],
    )


# ------------------------------------------------------------------ users
@bp.get("/api/admin/users")
@login_required
@admin_required
def users():
    q = clean_text(request.args.get("q"), 100)
    query = User.query
    if q:
        like = f"%{q}%"
        query = query.filter((User.name.ilike(like)) | (User.email.ilike(like)))
    rows = query.order_by(User.created_at.desc()).limit(500).all()
    conv_counts = dict(db.session.query(Conversation.user_id, func.count(Conversation.id)).group_by(Conversation.user_id).all())
    storage = dict(db.session.query(File.user_id, func.sum(File.size)).group_by(File.user_id).all())
    out = []
    for u in rows:
        out.append({**u.to_dict(), "disabled": u.disabled, "last_seen_at": iso(u.last_seen_at),
                    "conversations": conv_counts.get(u.id, 0), "storage": storage.get(u.id) or 0,
                    "is_self": u.id == current_user.id})
    return jsonify(users=out)


@bp.patch("/api/admin/users/<int:uid>")
@login_required
@admin_required
def update_user(uid):
    u = db.session.get(User, uid)
    if not u:
        return jsonify(error="User not found."), 404
    data = body()
    if u.id == current_user.id and (data.get("disabled") or data.get("role") == "user"):
        return jsonify(error="You can't disable or demote your own account."), 400
    if "disabled" in data:
        u.disabled = bool(data["disabled"])
        u.session_version += 1  # kick active sessions
    if data.get("role") in ("user", "admin"):
        u.role = data["role"]
    db.session.commit()
    return jsonify(ok=True)


@bp.delete("/api/admin/users/<int:uid>")
@login_required
@admin_required
def delete_user(uid):
    u = db.session.get(User, uid)
    if not u:
        return jsonify(error="User not found."), 404
    if u.id == current_user.id:
        return jsonify(error="Delete your own account from Settings instead."), 400
    from .api import delete_user_data
    delete_user_data(u)
    return jsonify(ok=True)


# ------------------------------------------------------------------ models
MODEL_FIELDS = {"slug": 80, "name": 120, "description": 300, "provider": 80, "model_family": 120, "api_base": 300,
                "api_model": 200, "api_key_env": 80, "badge": 30}


def model_admin_dict(m):
    key = resolve_key(m)
    return {"id": m.id, **{f: getattr(m, f) for f in MODEL_FIELDS}, "key_required": m.key_required,
            "supports_vision": m.supports_vision, "supports_streaming": m.supports_streaming,
            "temperature": m.temperature, "max_tokens": m.max_tokens, "context_chars": m.context_chars,
            "enabled": m.enabled, "sort_order": m.sort_order, "available": is_available(m),
            "key_status": ("stored in database" if m.api_key else (f"from {m.api_key_env}" if key else "missing")),
            "key_hint": ("••••" + key[-4:]) if key else ""}


def apply_model_fields(m, data):
    for f, n in MODEL_FIELDS.items():
        if f in data:
            setattr(m, f, clean_text(data[f], n))
    for f in ("key_required", "supports_vision", "supports_streaming", "enabled"):
        if f in data:
            setattr(m, f, bool(data[f]))
    for f, cast, lo, hi in (("temperature", float, 0, 2), ("max_tokens", int, 16, 64000),
                            ("context_chars", int, 2000, 500000), ("sort_order", int, 0, 10000)):
        if f in data and data[f] not in (None, ""):
            try:
                setattr(m, f, max(lo, min(hi, cast(data[f]))))
            except (TypeError, ValueError):
                pass
    if "api_key" in data and data["api_key"] != "__keep__":
        m.api_key = clean_text(data["api_key"], 500)
    if not m.slug or not m.api_base or not m.api_model or not m.name:
        raise ValueError("Name, slug, API base URL and API model are required.")
    if not m.api_base.startswith(("http://", "https://")):
        raise ValueError("API base URL must start with http:// or https://")


@bp.get("/api/admin/models")
@login_required
@admin_required
def list_models():
    return jsonify(models=[model_admin_dict(m) for m in AIModel.query.order_by(AIModel.sort_order, AIModel.id)])


@bp.post("/api/admin/models")
@login_required
@admin_required
def create_model():
    data = body()
    m = AIModel()
    try:
        apply_model_fields(m, data)
    except ValueError as exc:
        return jsonify(error=str(exc)), 400
    if AIModel.query.filter_by(slug=m.slug).first():
        return jsonify(error="A model with this slug already exists."), 400
    db.session.add(m)
    db.session.commit()
    return jsonify(ok=True, model=model_admin_dict(m))


@bp.patch("/api/admin/models/<int:mid>")
@login_required
@admin_required
def update_model(mid):
    m = db.session.get(AIModel, mid)
    if not m:
        return jsonify(error="Model not found."), 404
    try:
        apply_model_fields(m, body())
    except ValueError as exc:
        db.session.rollback()
        return jsonify(error=str(exc)), 400
    clash = AIModel.query.filter(AIModel.slug == m.slug, AIModel.id != m.id).first()
    if clash:
        db.session.rollback()
        return jsonify(error="A model with this slug already exists."), 400
    db.session.commit()
    return jsonify(ok=True, model=model_admin_dict(m))


@bp.delete("/api/admin/models/<int:mid>")
@login_required
@admin_required
def delete_model(mid):
    m = db.session.get(AIModel, mid)
    if m:
        db.session.delete(m)
        db.session.commit()
    return jsonify(ok=True)


@bp.post("/api/admin/models/<int:mid>/test")
@login_required
@admin_required
def test_model(mid):
    m = db.session.get(AIModel, mid)
    if not m:
        return jsonify(error="Model not found."), 404
    if not is_available(m):
        return jsonify(ok=False, error=f"No API key. Set {m.api_key_env} in .env or paste a key in the model form.")
    try:
        reply = complete(m, [{"role": "user", "content": "Reply with exactly: Cybok test OK"}], max_tokens=400, timeout=40)
        return jsonify(ok=True, reply=reply[:300] or "(empty reply - the model may only return reasoning)")
    except ProviderError as exc:
        return jsonify(ok=False, error=str(exc))


# ------------------------------------------------------------------ system settings
ENV_KEYS = ["GROQ_API_KEY", "OPENROUTER_API_KEY", "HF_TOKEN", "POLLINATIONS_TOKEN", "GOOGLE_CLIENT_ID",
            "GOOGLE_CLIENT_SECRET", "MAIL_SERVER", "SECRET_KEY"]


@bp.get("/api/admin/settings")
@login_required
@admin_required
def get_settings():
    s = all_settings()
    return jsonify(
        settings=s,
        env={k: bool(os.getenv(k)) for k in ENV_KEYS},
        image_providers=[{"key": k, "label": v[0]} for k, v in IMAGE_PROVIDERS.items()],
        models=[{"slug": m.slug, "name": m.name} for m in AIModel.query.order_by(AIModel.sort_order)],
        app={"version": current_app.config["VERSION"], "database": db.engine.dialect.name},
    )


@bp.get("/api/admin/keys")
@login_required
@admin_required
def get_keys():
    from ..ai.chat import FREE_KEYS
    from ..appsettings import get_setting
    out = []
    for name, (label, url) in FREE_KEYS.items():
        env_val = os.getenv(name, "").strip()
        db_val = get_setting(f"key:{name}").strip()
        val = env_val or db_val
        out.append({"name": name, "label": label, "url": url, "set": bool(val),
                    "source": "env" if env_val else ("admin" if db_val else None),
                    "hint": ("••••" + val[-4:]) if val else ""})
    return jsonify(keys=out)


@bp.patch("/api/admin/keys")
@login_required
@admin_required
def update_keys():
    from ..ai.chat import FREE_KEYS, _local_cache
    data = body()
    for name in FREE_KEYS:
        if name in data:
            set_setting(f"key:{name}", clean_text(data[name], 500))
    db.session.commit()
    _local_cache.clear()
    return get_keys()


@bp.patch("/api/admin/settings")
@login_required
@admin_required
def update_settings():
    data = body()
    if "creation_date" in data:
        raw = clean_text(data["creation_date"], 20)
        if raw:
            try:
                date.fromisoformat(raw)
            except ValueError:
                return jsonify(error="Creation date must be a valid date (YYYY-MM-DD)."), 400
        set_setting("creation_date", raw)
    if "registration_open" in data:
        set_setting("registration_open", "1" if data["registration_open"] else "0")
    if "max_upload_mb" in data:
        try:
            set_setting("max_upload_mb", str(max(1, min(200, int(data["max_upload_mb"])))))
        except (TypeError, ValueError):
            return jsonify(error="Max upload size must be a number."), 400
    if "system_prompt_extra" in data:
        set_setting("system_prompt_extra", clean_text(data["system_prompt_extra"], 2000))
    if data.get("image_provider") in IMAGE_PROVIDERS:
        set_setting("image_provider", data["image_provider"])
    for k, n in (("image_model", 60), ("hf_image_model", 200), ("default_model", 80), ("maintenance_message", 300)):
        if k in data:
            set_setting(k, clean_text(data[k], n))
    db.session.commit()
    return jsonify(ok=True, settings=all_settings())


# ------------------------------------------------------------------ announcements
@bp.get("/api/admin/announcements")
@login_required
@admin_required
def list_announcements():
    return jsonify(announcements=[a.to_dict() for a in Announcement.query.order_by(Announcement.created_at.desc())])


@bp.post("/api/admin/announcements")
@login_required
@admin_required
def create_announcement():
    data = body()
    title = clean_text(data.get("title"), 200)
    if not title:
        return jsonify(error="Title is required."), 400
    a = Announcement(title=title, body=clean_text(data.get("body"), 2000),
                     level=data.get("level") if data.get("level") in ("info", "success", "warning") else "info",
                     active=bool(data.get("active", True)))
    db.session.add(a)
    db.session.commit()
    return jsonify(ok=True, announcement=a.to_dict())


@bp.patch("/api/admin/announcements/<int:aid>")
@login_required
@admin_required
def update_announcement(aid):
    a = db.session.get(Announcement, aid)
    if not a:
        return jsonify(error="Not found."), 404
    data = body()
    if "title" in data:
        a.title = clean_text(data["title"], 200) or a.title
    if "body" in data:
        a.body = clean_text(data["body"], 2000)
    if data.get("level") in ("info", "success", "warning"):
        a.level = data["level"]
    if "active" in data:
        a.active = bool(data["active"])
    db.session.commit()
    return jsonify(ok=True, announcement=a.to_dict())


@bp.delete("/api/admin/announcements/<int:aid>")
@login_required
@admin_required
def delete_announcement(aid):
    a = db.session.get(Announcement, aid)
    if a:
        db.session.delete(a)
        db.session.commit()
    return jsonify(ok=True)


# ------------------------------------------------------------------ errors
@bp.get("/api/admin/errors")
@login_required
@admin_required
def errors():
    rows = ErrorLog.query.order_by(ErrorLog.created_at.desc()).limit(300).all()
    return jsonify(errors=[e.to_dict() for e in rows])


@bp.delete("/api/admin/errors")
@login_required
@admin_required
def clear_errors():
    ErrorLog.query.delete()
    db.session.commit()
    return jsonify(ok=True)
