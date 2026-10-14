"""JSON API used by the Cybok web app. Every query is scoped to current_user."""
import base64
import io
import json
import re
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

from flask import Blueprint, Response, current_app, jsonify, request, stream_with_context
from flask_login import current_user, logout_user
from PIL import Image
from sqlalchemy import or_

from ..ai import images as image_ai
from ..ai import logos as logo_ai
from ..ai.chat import (ProviderError, complete, default_model_slug, enabled_models, fallback_models, get_model,
                       model_public, stream_chat)
from ..appsettings import get_setting
from ..extensions import db
from ..files import (UploadError, abs_path, delete_file_blob, handle_upload, safe_display_name, save_bytes)
from ..identity import identity_reply, system_prompt
from ..mailer import mail_configured, send_mail
from ..models import (Announcement, Conversation, File, GeneratedContent, Message, User, UserSettings, iso,
                      utcnow)
from ..security import (api_login_required, clean_text, log_error, log_usage, password_problem, rate_limit,
                        valid_email)

bp = Blueprint("api", __name__, url_prefix="/api")

STOP_FLAGS = set()
MAX_ATTACHMENTS = 8


# ------------------------------------------------------------------ helpers
def ok(**data):
    return jsonify(ok=True, **data)


def err(message, status=400):
    return jsonify(error=message), status


def body():
    return request.get_json(silent=True) or {}


def settings_for(user):
    if not user.settings:
        user.settings = UserSettings()
        db.session.commit()
    return user.settings


def own_conv(cid, include_deleted=False):
    q = Conversation.query.filter_by(id=cid, user_id=current_user.id)
    if not include_deleted:
        q = q.filter(Conversation.deleted_at.is_(None))
    conv = q.first()
    if conv is None:
        from flask import abort
        resp = jsonify(error="Conversation not found.")
        resp.status_code = 404
        abort(resp)
    return conv


def files_by_id(ids):
    if not ids:
        return {}
    rows = File.query.filter(File.id.in_(ids), File.user_id == current_user.id).all()
    return {f.id: f for f in rows}


def message_dict(m, fmap):
    return m.to_dict([fmap[i].to_dict() for i in m.attachment_ids if i in fmap])


def max_upload_mb():
    try:
        return max(1, min(200, int(get_setting("max_upload_mb") or current_app.config["MAX_UPLOAD_MB"])))
    except ValueError:
        return current_app.config["MAX_UPLOAD_MB"]


def sse(obj):
    return f"data: {json.dumps(obj, ensure_ascii=False)}\n\n"


def heuristic_title(text):
    t = re.sub(r"[`*_#>\[\]()!]+", "", text or "").strip().splitlines()
    t = (t[0] if t else "").strip()
    if not t:
        return "New chat"
    if len(t) <= 52:
        return t[0].upper() + t[1:]
    cut = t[:52].rsplit(" ", 1)[0]
    return (cut or t[:52]).rstrip(",.;:") + "…"


def purge_old(user_id):
    """House-keeping: trash older than 30 days and stale temporary chats are removed."""
    cutoff = utcnow() - timedelta(days=30)
    Conversation.query.filter(Conversation.user_id == user_id, Conversation.deleted_at.isnot(None),
                              Conversation.deleted_at < cutoff).delete(synchronize_session=False)
    Conversation.query.filter(Conversation.user_id == user_id, Conversation.temporary.is_(True),
                              Conversation.updated_at < utcnow() - timedelta(hours=12)).delete(synchronize_session=False)
    db.session.commit()


# ------------------------------------------------------------------ bootstrap
@bp.get("/bootstrap")
@api_login_required
def bootstrap():
    purge_old(current_user.id)
    current_user.last_seen_at = utcnow()
    db.session.commit()
    s = settings_for(current_user)
    default_slug = default_model_slug()
    models = [model_public(m, default_slug) for m in enabled_models()]
    convs = (Conversation.query.filter_by(user_id=current_user.id, temporary=False)
             .filter(Conversation.deleted_at.is_(None))
             .order_by(Conversation.updated_at.desc()).limit(500).all())
    anns = Announcement.query.filter_by(active=True).order_by(Announcement.created_at.desc()).limit(3).all()
    return jsonify(
        user=current_user.to_dict(),
        settings=s.to_dict(),
        models=models,
        default_model=s.default_model if any(m["slug"] == s.default_model and m["available"] for m in models) else default_slug,
        conversations=[c.to_dict() for c in convs],
        announcements=[a.to_dict() for a in anns],
        limits={"max_upload_mb": max_upload_mb(), "max_attachments": MAX_ATTACHMENTS},
        image_styles=[{"key": k, "label": v[0]} for k, v in image_ai.STYLES.items()],
        image_sizes=list(image_ai.SIZES.keys()),
        mail_configured=mail_configured(),
        app={"name": "Cybok", "version": current_app.config["VERSION"], "creator": current_app.config["CREATOR_NAME"],
             "creator_description": current_app.config["CREATOR_DESCRIPTION"]},
    )


# ------------------------------------------------------------------ conversations
@bp.get("/chats")
@api_login_required
def list_chats():
    q = Conversation.query.filter_by(user_id=current_user.id, temporary=False)
    if request.args.get("trash"):
        q = q.filter(Conversation.deleted_at.isnot(None))
    else:
        q = q.filter(Conversation.deleted_at.is_(None))
        if request.args.get("archived"):
            q = q.filter_by(archived=True)
    return jsonify(conversations=[c.to_dict() for c in q.order_by(Conversation.updated_at.desc()).limit(1000)])


@bp.post("/chats")
@api_login_required
def create_chat():
    data = body()
    s = settings_for(current_user)
    m = get_model(data.get("model") or s.default_model)
    conv = Conversation(user_id=current_user.id, model=m.slug if m else None,
                        temporary=bool(data.get("temporary")) or not s.save_history)
    db.session.add(conv)
    db.session.commit()
    return ok(conversation=conv.to_dict())


@bp.get("/chats/<cid>")
@api_login_required
def get_chat(cid):
    conv = own_conv(cid, include_deleted=True)
    msgs = conv.messages.all()
    ids = {i for m in msgs for i in m.attachment_ids}
    fmap = files_by_id(list(ids))
    return jsonify(conversation=conv.to_dict(), messages=[message_dict(m, fmap) for m in msgs])


@bp.patch("/chats/<cid>")
@api_login_required
def update_chat(cid):
    conv = own_conv(cid)
    data = body()
    if "title" in data:
        title = clean_text(data["title"], 200)
        conv.title = title or "New chat"
    if "pinned" in data:
        conv.pinned = bool(data["pinned"])
    if "archived" in data:
        conv.archived = bool(data["archived"])
        if conv.archived:
            conv.pinned = False
    if "model" in data:
        m = get_model(data["model"])
        if m:
            conv.model = m.slug
    if "temporary" in data and not data["temporary"]:
        conv.temporary = False
    db.session.commit()
    return ok(conversation=conv.to_dict())


@bp.delete("/chats/<cid>")
@api_login_required
def delete_chat(cid):
    conv = own_conv(cid, include_deleted=True)
    if request.args.get("permanent") or conv.deleted_at is not None or conv.temporary:
        db.session.delete(conv)
    else:
        conv.deleted_at = utcnow()
        conv.pinned = False
        conv.share_enabled = False
    db.session.commit()
    return ok()


@bp.post("/chats/<cid>/restore")
@api_login_required
def restore_chat(cid):
    conv = own_conv(cid, include_deleted=True)
    conv.deleted_at = None
    db.session.commit()
    return ok(conversation=conv.to_dict())


@bp.delete("/chats")
@api_login_required
def delete_all_chats():
    scope = request.args.get("scope", "all")
    q = Conversation.query.filter_by(user_id=current_user.id)
    if scope == "trash":
        q = q.filter(Conversation.deleted_at.isnot(None))
    elif scope == "archived":
        q = q.filter_by(archived=True)
    count = 0
    for c in q.all():
        db.session.delete(c)
        count += 1
    db.session.commit()
    return ok(deleted=count)


@bp.post("/chats/<cid>/share")
@api_login_required
def share_chat(cid):
    conv = own_conv(cid)
    data = body()
    enabled = bool(data.get("enabled", True))
    if data.get("regenerate"):
        conv.share_token = None
    if enabled:
        conv.ensure_share_token()
        conv.share_enabled = True
        conv.shared_at = utcnow()
        conv.temporary = False
    else:
        conv.share_enabled = False
    db.session.commit()
    return ok(conversation=conv.to_dict())


@bp.get("/shares")
@api_login_required
def list_shares():
    rows = Conversation.query.filter_by(user_id=current_user.id, share_enabled=True).filter(
        Conversation.deleted_at.is_(None)).all()
    return jsonify(shares=[c.to_dict() for c in rows])


@bp.get("/chats/<cid>/export")
@api_login_required
def export_chat(cid):
    conv = own_conv(cid, include_deleted=True)
    lines = [f"# {conv.title}", "", f"_Exported from Cybok — {utcnow():%Y-%m-%d %H:%M} UTC_", ""]
    for m in conv.messages:
        who = "You" if m.role == "user" else "Cybok"
        lines += [f"### {who}", "", m.content or "", ""]
    name = re.sub(r"[^A-Za-z0-9 _-]", "", conv.title)[:60].strip() or "chat"
    return Response("\n".join(lines), mimetype="text/markdown",
                    headers={"Content-Disposition": f'attachment; filename="{name}.md"'})


# ------------------------------------------------------------------ messaging
def _image_part(f):
    """Downscaled JPEG data URL for vision models."""
    try:
        with Image.open(abs_path(f.storage_path)) as im:
            im = im.convert("RGB")
            im.thumbnail((1280, 1280))
            buf = io.BytesIO()
            im.save(buf, "JPEG", quality=85)
        return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()
    except Exception:
        return None


def build_messages(conv, model, settings, upto_id):
    msgs = [m for m in conv.messages.filter(Message.id <= upto_id).all()
            if m.status != "error" and (m.content or m.attachment_ids)]
    all_ids = []
    for m in msgs:
        for i in m.attachment_ids:
            if i not in all_ids:
                all_ids.append(i)
    fmap = files_by_id(all_ids)
    budget = max(4000, model.context_chars or 24000)

    # Documents attached anywhere in this chat are given to the model as context (newest first).
    docs = [fmap[i] for i in reversed(all_ids) if i in fmap and fmap[i].kind != "image" and fmap[i].extracted_text]
    doc_budget = int(budget * 0.6)
    doc_blocks = []
    if docs:
        per = max(1500, doc_budget // len(docs))
        for f in docs:
            text = f.extracted_text
            clipped = text[:per]
            note = f"\n[... truncated: showing {len(clipped):,} of {len(text):,} characters]" if len(text) > per else ""
            doc_blocks.append(f"### File: {f.name}\n```\n{clipped}\n```{note}")
            doc_budget -= len(clipped)
            if doc_budget <= 0:
                break
    sys = system_prompt(model, settings, get_setting("system_prompt_extra"))
    if doc_blocks:
        sys += ("\n\nThe user attached the following files to this conversation. Use them to answer questions, "
                "quote numbers exactly, and say when something is not in the files.\n\n" + "\n\n".join(doc_blocks))
    remaining = budget - sum(len(b) for b in doc_blocks)

    out = []
    last_user = max((m.id for m in msgs if m.role == "user"), default=None)
    for m in reversed(msgs):
        text = m.content or ""
        if m.role == "assistant":
            text = re.sub(r"<think>.*?</think>\s*", "", text, flags=re.S)
        images = [fmap[i] for i in m.attachment_ids if i in fmap and fmap[i].kind == "image"]
        other = [fmap[i] for i in m.attachment_ids if i in fmap and fmap[i].kind != "image"]
        if other:
            text += "\n\n(Attached: " + ", ".join(f.name for f in other) + ")"
        if images and m.role == "user":
            if model.supports_vision and m.id == last_user:
                parts = [{"type": "text", "text": text or "Describe this image."}]
                for f in images[:4]:
                    url = _image_part(f)
                    if url:
                        parts.append({"type": "image_url", "image_url": {"url": url}})
                out.append({"role": "user", "content": parts})
                remaining -= len(text)
                continue
            text += "\n\n(" + "; ".join(
                f"Image attached: {f.name}, {f.meta_dict.get('width', '?')}x{f.meta_dict.get('height', '?')} px"
                for f in images) + (". The current model cannot see images - if the user asks about the image, "
                                     "politely suggest switching to a model with Vision.)" if not model.supports_vision else ")")
        if remaining - len(text) < 0 and out:
            break
        remaining -= len(text)
        out.append({"role": m.role, "content": text})
    out.reverse()
    while out and out[0]["role"] == "assistant":
        out.pop(0)
    return [{"role": "system", "content": sys}] + out


@bp.post("/chats/<cid>/messages")
@api_login_required
@rate_limit("chat", "RATE_CHAT_PER_MIN")
def send_message(cid):
    conv = own_conv(cid)
    data = body()
    s = settings_for(current_user)
    model = get_model(data.get("model") or conv.model or s.default_model)
    if model is None:
        return err("No AI model is ready yet. An admin can turn one on for free in Admin > System (paste a free Groq key) or by installing Ollama - see the user manual.", 503)

    mode = data.get("mode", "send")  # send | regenerate | edit
    if mode == "regenerate":
        last_user = conv.messages.filter_by(role="user").order_by(Message.id.desc()).first()
        if not last_user:
            return err("Nothing to regenerate.")
        Message.query.filter(Message.conversation_id == conv.id, Message.id > last_user.id).delete(synchronize_session=False)
        user_msg = last_user
    elif mode == "edit":
        user_msg = conv.messages.filter_by(id=data.get("message_id"), role="user").first()
        if not user_msg:
            return err("Message not found.", 404)
        content = clean_text(data.get("content"), 60000)
        if not content:
            return err("Message can't be empty.")
        user_msg.content = content
        Message.query.filter(Message.conversation_id == conv.id, Message.id > user_msg.id).delete(synchronize_session=False)
    else:
        content = clean_text(data.get("content"), 60000)
        att = [str(a) for a in (data.get("attachments") or [])][:MAX_ATTACHMENTS]
        fmap = files_by_id(att)
        att = [a for a in att if a in fmap]
        if not content and not att:
            return err("Type a message or attach a file.")
        user_msg = Message(conversation_id=conv.id, role="user", content=content, attachments=json.dumps(att))
        db.session.add(user_msg)
        db.session.flush()

    first_turn = conv.title == "New chat"
    if first_turn:
        conv.title = heuristic_title(user_msg.content or "Files")
    assistant = Message(conversation_id=conv.id, role="assistant", content="", model=model.slug, status="streaming")
    db.session.add(assistant)
    conv.model = model.slug
    conv.updated_at = utcnow()
    db.session.commit()

    history = build_messages(conv, model, s, user_msg.id)
    fmap = files_by_id(user_msg.attachment_ids)
    user_payload = message_dict(user_msg, fmap)
    asst_id, user_id, user_text, user_msg_id = assistant.id, current_user.id, user_msg.content or "", user_msg.id
    model_info = model_public(model)
    timeout = current_app.config["AI_TIMEOUT"]
    has_images = any(f.kind == "image" for f in fmap.values())
    used = {"model": model}

    def generate():
        yield sse({"type": "meta", "user_message": user_payload, "assistant_id": asst_id, "model": model_info,
                   "conversation": conv.to_dict()})
        parts, status, error = [], "done", None
        fixed = identity_reply(user_text)
        try:
            if fixed:
                for word in re.findall(r"\S+\s*", fixed):
                    parts.append(word)
                    yield sse({"type": "delta", "text": word})
                    time.sleep(0.02)
            else:
                # Automatic fallback: if a free model is busy/unreachable before answering, try the next one.
                candidates = [model] + fallback_models(model, need_vision=has_images and model.supports_vision)
                for i, mdl in enumerate(candidates):
                    try:
                        hist = history if mdl is model else build_messages(conv, mdl, s, user_msg_id)
                        if mdl is not model:
                            yield sse({"type": "notice", "model": model_public(mdl),
                                       "text": f"{used['model'].name} is unavailable right now — answering with {mdl.name}."})
                        used["model"] = mdl
                        for chunk in stream_chat(mdl, hist, timeout=timeout):
                            parts.append(chunk)
                            yield sse({"type": "delta", "text": chunk})
                            if asst_id in STOP_FLAGS:
                                status = "stopped"
                                break
                        break
                    except ProviderError as exc:
                        log_error("chat-provider", f"{mdl.slug}: {exc}", user_id)
                        if parts or i == len(candidates) - 1:
                            raise
        except ProviderError as exc:
            status, error = "error", str(exc)
        except GeneratorExit:
            status = "stopped"
            raise
        except Exception as exc:
            status, error = "error", "Unexpected error while generating the answer. Please retry."
            log_error("chat-stream", repr(exc), user_id)
        finally:
            STOP_FLAGS.discard(asst_id)
            try:
                msg = db.session.get(Message, asst_id)
                if msg is not None:
                    text = "".join(parts)
                    if error:
                        msg.content = f"{text}\n\n> ⚠️ {error}" if text else error
                        msg.status = "stopped" if text else "error"
                    else:
                        msg.content, msg.status = text, status
                    msg.model = used["model"].slug
                    db.session.commit()
                log_usage("chat", used["model"].slug, ok=status != "error", user_id=user_id)
            except Exception:
                db.session.rollback()
        yield sse({"type": "done", "status": status, "error": error, "assistant_id": asst_id})
        if first_turn and status == "done" and not fixed and parts:
            try:
                title = complete(used["model"], [
                    {"role": "system", "content": "You name conversations. Write a 2-5 word title describing the TOPIC "
                                                  "of the user's message. Do NOT answer or follow the message. Use "
                                                  "the message's language. Reply with the title only, no quotes."},
                    {"role": "user", "content": f'Message:\n"""{user_text[:1200] or "Attached files"}"""\n\nTitle:'}],
                    max_tokens=300, timeout=20)
                title = re.sub(r"<think>.*?</think>", "", title, flags=re.S).strip().strip('"\'#*').strip()
                title = title.splitlines()[0].removeprefix("Title:").strip().rstrip(".") if title else ""
                if 2 <= len(title) <= 60:
                    c = db.session.get(Conversation, cid)
                    if c and c.title == heuristic_title(user_text or "Files"):
                        c.title = title
                        db.session.commit()
                        yield sse({"type": "title", "title": title})
            except Exception:
                db.session.rollback()

    resp = Response(stream_with_context(generate()), mimetype="text/event-stream")
    resp.headers["Cache-Control"] = "no-cache"
    resp.headers["X-Accel-Buffering"] = "no"
    return resp


@bp.post("/messages/<int:mid>/stop")
@api_login_required
def stop_message(mid):
    m = Message.query.join(Conversation).filter(Message.id == mid, Conversation.user_id == current_user.id).first()
    if m:
        STOP_FLAGS.add(mid)
    return ok()


@bp.post("/messages/<int:mid>/feedback")
@api_login_required
def feedback(mid):
    m = Message.query.join(Conversation).filter(Message.id == mid, Conversation.user_id == current_user.id).first()
    if not m:
        return err("Message not found.", 404)
    v = int(body().get("value", 0))
    m.feedback = v if v in (-1, 0, 1) else 0
    db.session.commit()
    return ok(feedback=m.feedback)


@bp.post("/messages/<int:mid>/save")
@api_login_required
def save_message(mid):
    m = Message.query.join(Conversation).filter(Message.id == mid, Conversation.user_id == current_user.id).first()
    if not m:
        return err("Message not found.", 404)
    text = re.sub(r"<think>.*?</think>\s*", "", m.content or "", flags=re.S).strip()
    title = clean_text(body().get("title"), 200) or heuristic_title(m.conversation.title + " — response")
    g = GeneratedContent(user_id=current_user.id, content_type="text", title=title, output=text,
                         prompt=m.conversation.title, saved=True, meta=json.dumps({"model": m.model}))
    db.session.add(g)
    db.session.commit()
    return ok(item=g.to_dict())


@bp.post("/chats/<cid>/image")
@api_login_required
@rate_limit("image", "RATE_IMAGE_PER_MIN")
def chat_image(cid):
    """Image generation from inside a conversation: the result becomes part of the chat."""
    conv = own_conv(cid)
    data = body()
    prompt = clean_text(data.get("prompt"), 1500)
    if not prompt:
        return err("Describe the image you want.")
    style = data.get("style") if data.get("style") in image_ai.STYLES else "none"
    size = data.get("size") if data.get("size") in image_ai.SIZES else "square"
    user_msg = Message(conversation_id=conv.id, role="user", content=f"\U0001f3a8 Create image: {prompt}")
    db.session.add(user_msg)
    if conv.title == "New chat":
        conv.title = heuristic_title("Image: " + prompt)
    db.session.commit()
    try:
        g = _generate_images(prompt, style, size, 1, "image")[0]
    except image_ai.ImageError as exc:
        a = Message(conversation_id=conv.id, role="assistant", content=f"⚠️ {exc}", status="error",
                    model="image")
        db.session.add(a)
        conv.updated_at = utcnow()
        db.session.commit()
        return jsonify(user_message=message_dict(user_msg, {}), assistant_message=message_dict(a, {}),
                       conversation=conv.to_dict(), error=str(exc)), 200
    meta = json.loads(g.meta or "{}")
    a = Message(conversation_id=conv.id, role="assistant", model="image",
                content=f"Here's your image — *{prompt}*\n\n![{prompt.replace(']', '')}](/media/file/{g.file_id})\n\n"
                        f"<sub>Generated with {meta.get('provider', 'image model')} · style: "
                        f"{image_ai.STYLES[style][0]} · seed {meta.get('seed')}</sub>")
    db.session.add(a)
    conv.updated_at = utcnow()
    db.session.commit()
    return jsonify(user_message=message_dict(user_msg, {}), assistant_message=message_dict(a, {}),
                   conversation=conv.to_dict(), item=g.to_dict())


# ------------------------------------------------------------------ images & logos
def _generate_images(prompt, style, size, count, content_type, extra_meta=None, prompts=None, seeds=None):
    cfg = image_ai.image_config()
    prompts = prompts or [prompt] * count
    seeds = seeds or [None] * len(prompts)
    # The keyless image tier allows one request at a time, so generate sequentially unless a token is set.
    keyless = cfg.get("image_provider", "pollinations") == "pollinations" and not cfg.get("pollinations_token")
    with ThreadPoolExecutor(max_workers=1 if keyless else min(4, len(prompts))) as pool:
        futures = [pool.submit(image_ai.generate, p, cfg, style, size, sd) for p, sd in zip(prompts, seeds)]
        results, errors = [], []
        for fut in futures:
            try:
                results.append(fut.result())
            except image_ai.ImageError as exc:
                errors.append(str(exc))
                log_error("image", str(exc))
            except Exception as exc:
                errors.append("Image generation failed.")
                log_error("image", repr(exc))
    if not results:
        log_usage(content_type, cfg.get("image_provider"), ok=False)
        raise image_ai.ImageError(errors[0] if errors else "Image generation failed.")
    items = []
    for data, mime, label, seed in results:
        ext = {"image/png": "png", "image/webp": "webp"}.get(mime, "jpg")
        name = safe_display_name(re.sub(r"\s+", "-", prompt[:40]).strip("-") or "image") + f".{ext}"
        f = save_bytes(current_user.id, data, name, mime=mime, source="generated", in_library=False)
        meta = {"provider": label, "seed": seed, "size": size, **(extra_meta or {})}
        g = GeneratedContent(user_id=current_user.id, content_type=content_type, title=prompt[:120], prompt=prompt,
                             file_id=f.id, style=style, meta=json.dumps(meta), saved=False)
        db.session.add(g)
        items.append(g)
        log_usage(content_type, label)
    db.session.commit()
    return items


@bp.post("/images")
@api_login_required
@rate_limit("image", "RATE_IMAGE_PER_MIN")
def create_images():
    data = body()
    prompt = clean_text(data.get("prompt"), 1500)
    if len(prompt) < 3:
        return err("Describe the image you want (at least a few words).")
    style = data.get("style") if data.get("style") in image_ai.STYLES else "none"
    size = data.get("size") if data.get("size") in image_ai.SIZES else "square"
    count = max(1, min(4, int(data.get("count") or 1)))
    seed = data.get("seed")
    seeds = [int(seed) + i for i in range(count)] if isinstance(seed, int) else None
    try:
        items = _generate_images(prompt, style, size, count, "image", seeds=seeds)
    except image_ai.ImageError as exc:
        return err(str(exc), 502)
    return ok(items=[g.to_dict() for g in items])


@bp.get("/generated")
@api_login_required
def list_generated():
    ctype = request.args.get("type", "image")
    q = GeneratedContent.query.filter_by(user_id=current_user.id)
    if ctype != "all":
        q = q.filter_by(content_type=ctype)
    rows = q.order_by(GeneratedContent.created_at.desc()).limit(min(200, int(request.args.get("limit", 60)))).all()
    return jsonify(items=[g.to_dict() for g in rows])


@bp.patch("/generated/<gid>")
@api_login_required
def update_generated(gid):
    g = GeneratedContent.query.filter_by(id=gid, user_id=current_user.id).first()
    if not g:
        return err("Item not found.", 404)
    data = body()
    if "saved" in data:
        g.saved = bool(data["saved"])
        if g.file:
            g.file.in_library = False  # the generated item itself represents it in the Library
    if "title" in data:
        g.title = clean_text(data["title"], 200) or g.title
    if "folder" in data:
        g.folder = clean_text(data["folder"], 80)
    db.session.commit()
    return ok(item=g.to_dict())


@bp.delete("/generated/<gid>")
@api_login_required
def delete_generated(gid):
    g = GeneratedContent.query.filter_by(id=gid, user_id=current_user.id).first()
    if not g:
        return err("Item not found.", 404)
    f = g.file
    db.session.delete(g)
    if f:
        delete_file_blob(f)
        db.session.delete(f)
    db.session.commit()
    return ok()


@bp.post("/logos")
@api_login_required
@rate_limit("image", "RATE_IMAGE_PER_MIN")
def create_logos():
    data = body()
    fields = {k: clean_text(data.get(k), 120) for k in ("brand", "industry", "style", "colors", "symbol", "typography")}
    if not fields["brand"]:
        return err("Enter a brand name.")
    batch = logo_ai.svg_fingerprint(json.dumps(fields) + str(time.time()))
    items = []
    for concept in logo_ai.generate_concepts(**fields):
        g = GeneratedContent(user_id=current_user.id, content_type="logo", title=f"{fields['brand']} — {concept['title']}",
                             prompt=json.dumps(fields), output=concept["svg"], style="vector",
                             meta=json.dumps({"kind": "vector", "concept": concept["title"], "batch": batch, **fields}))
        db.session.add(g)
        items.append(g)
    db.session.commit()
    log_usage("logo", "vector")
    ai_error = None
    ai_count = max(0, min(4, int(data.get("ai_count") or 0)))
    if ai_count:
        prompts = [logo_ai.ai_logo_prompt(variant=i, **fields) for i in range(ai_count)]
        try:
            ai_items = _generate_images(fields["brand"], "none", "square", ai_count, "logo", prompts=prompts,
                                        extra_meta={"kind": "ai", "batch": batch, **fields})
            for g in ai_items:
                g.title = f"{fields['brand']} — AI concept"
            db.session.commit()
            items = ai_items + items
        except image_ai.ImageError as exc:
            ai_error = str(exc)
    return ok(items=[g.to_dict() for g in items], ai_error=ai_error)


# ------------------------------------------------------------------ files & library
@bp.post("/files")
@api_login_required
@rate_limit("upload", "RATE_UPLOAD_PER_MIN")
def upload_file():
    storage = request.files.get("file")
    if storage is None or not storage.filename:
        return err("No file received.")
    try:
        f = handle_upload(current_user.id, storage, max_upload_mb())
        db.session.commit()
    except UploadError as exc:
        db.session.rollback()
        return err(str(exc))
    log_usage("upload", f.ext)
    return ok(file=f.to_dict())


@bp.get("/files/<fid>")
@api_login_required
def get_file(fid):
    f = File.query.filter_by(id=fid, user_id=current_user.id).first()
    if not f:
        return err("File not found.", 404)
    d = f.to_dict()
    d["text_preview"] = (f.extracted_text or "")[:20000]
    d["text_length"] = len(f.extracted_text or "")
    return jsonify(file=d)


def _library_item_file(f):
    return {"key": f"file:{f.id}", "type": f.kind, "source": "upload", "title": f.name, "subtitle": f.ext.upper(),
            "url": f"/media/file/{f.id}",
            "thumb": f"/media/file/{f.id}?thumb=1" if f.kind == "image" else None,
            "download_url": f"/media/file/{f.id}?download=1", "size": f.size, "folder": f.folder or "",
            "has_text": bool(f.extracted_text), "file_id": f.id, "created_at": iso(f.created_at)}


def _library_item_gen(g):
    d = g.to_dict()
    return {"key": f"gen:{g.id}", "type": g.content_type if g.content_type != "text" else "text",
            "source": "generated", "title": g.title or g.content_type.title(),
            "subtitle": {"image": "Generated image", "logo": "Logo concept", "text": "Saved response"}.get(g.content_type, ""),
            "url": d["url"], "thumb": (f"/media/file/{g.file_id}?thumb=1" if g.file_id else d["url"]),
            "download_url": d["download_url"], "size": g.file.size if g.file else len(g.output or ""),
            "folder": g.folder or "", "prompt": g.prompt if g.content_type != "logo" else None,
            "output": g.output if g.content_type == "text" else None, "gen_id": g.id,
            "created_at": iso(g.created_at)}


@bp.get("/library")
@api_login_required
def library():
    t = request.args.get("type", "all")
    q = clean_text(request.args.get("q"), 100).lower()
    folder = request.args.get("folder")
    sort = request.args.get("sort", "new")
    items = []
    if t in ("all", "upload", "document", "data", "code", "image"):
        fq = File.query.filter_by(user_id=current_user.id, source="upload", in_library=True)
        if t in ("document", "data", "code", "image"):
            fq = fq.filter_by(kind=t)
        items += [_library_item_file(f) for f in fq.limit(2000)]
    if t in ("all", "image", "logo", "text", "generated"):
        gq = GeneratedContent.query.filter_by(user_id=current_user.id, saved=True)
        if t in ("image", "logo", "text"):
            gq = gq.filter_by(content_type=t)
        items += [_library_item_gen(g) for g in gq.limit(2000)]
    if folder is not None and folder != "__all__":
        items = [i for i in items if i["folder"] == folder]
    if q:
        items = [i for i in items if q in (i["title"] or "").lower() or q in (i.get("prompt") or "").lower()
                 or q in (i.get("output") or "").lower()[:5000]]
    if sort == "name":
        items.sort(key=lambda i: (i["title"] or "").lower())
    elif sort == "size":
        items.sort(key=lambda i: i["size"] or 0, reverse=True)
    else:
        items.sort(key=lambda i: i["created_at"] or "", reverse=sort != "old")
    folders = sorted({f.folder for f in File.query.filter_by(user_id=current_user.id).all() if f.folder} |
                     {g.folder for g in GeneratedContent.query.filter_by(user_id=current_user.id, saved=True).all() if g.folder})
    used = sum(f.size or 0 for f in File.query.filter_by(user_id=current_user.id).all())
    return jsonify(items=items, folders=folders, storage_used=used)


def _resolve_key(key):
    kind, _, ident = (key or "").partition(":")
    if kind == "file":
        return "file", File.query.filter_by(id=ident, user_id=current_user.id).first()
    if kind == "gen":
        return "gen", GeneratedContent.query.filter_by(id=ident, user_id=current_user.id).first()
    return None, None


@bp.patch("/library/<key>")
@api_login_required
def update_library(key):
    kind, obj = _resolve_key(key)
    if not obj:
        return err("Item not found.", 404)
    data = body()
    if "title" in data:
        title = clean_text(data["title"], 200)
        if title:
            if kind == "file":
                ext = obj.ext
                obj.name = safe_display_name(title if not ext or title.lower().endswith("." + ext) else f"{title}.{ext}")
            else:
                obj.title = title
    if "folder" in data:
        obj.folder = clean_text(data["folder"], 80)
    db.session.commit()
    return ok(item=_library_item_file(obj) if kind == "file" else _library_item_gen(obj))


@bp.delete("/library/<key>")
@api_login_required
def delete_library(key):
    kind, obj = _resolve_key(key)
    if not obj:
        return err("Item not found.", 404)
    if kind == "file":
        delete_file_blob(obj)
        GeneratedContent.query.filter_by(file_id=obj.id).delete()
        db.session.delete(obj)
    else:
        f = obj.file
        db.session.delete(obj)
        if f:
            delete_file_blob(f)
            db.session.delete(f)
    db.session.commit()
    return ok()


# ------------------------------------------------------------------ search
def _snippet(text, q, width=90):
    if not text:
        return ""
    i = text.lower().find(q.lower())
    if i < 0:
        return text[:width * 2].replace("\n", " ")
    start = max(0, i - width)
    return ("…" if start else "") + text[start:i + len(q) + width].replace("\n", " ") + "…"


@bp.get("/search")
@api_login_required
def search():
    q = clean_text(request.args.get("q"), 100)
    if len(q) < 2:
        return jsonify(chats=[], files=[], generated=[])
    like = f"%{q.replace('%', '').replace('_', '')}%"
    uid = current_user.id
    base = Conversation.query.filter_by(user_id=uid, temporary=False).filter(Conversation.deleted_at.is_(None))
    title_hits = base.filter(Conversation.title.ilike(like)).order_by(Conversation.updated_at.desc()).limit(10).all()
    msg_hits = (db.session.query(Message, Conversation).join(Conversation)
                .filter(Conversation.user_id == uid, Conversation.temporary.is_(False), Conversation.deleted_at.is_(None),
                        Message.content.ilike(like))
                .order_by(Message.id.desc()).limit(40).all())
    chats, seen = [], set()
    for c in title_hits:
        seen.add(c.id)
        chats.append({**c.to_dict(), "snippet": ""})
    for m, c in msg_hits:
        if c.id not in seen and len(chats) < 15:
            seen.add(c.id)
            chats.append({**c.to_dict(), "snippet": _snippet(m.content, q), "message_id": m.id})
    files = File.query.filter(File.user_id == uid, File.source == "upload",
                              or_(File.name.ilike(like), File.extracted_text.ilike(like))).limit(10).all()
    gens = GeneratedContent.query.filter(GeneratedContent.user_id == uid,
                                         or_(GeneratedContent.title.ilike(like), GeneratedContent.prompt.ilike(like),
                                             GeneratedContent.output.ilike(like) & (GeneratedContent.content_type == "text"))
                                         ).order_by(GeneratedContent.created_at.desc()).limit(10).all()
    return jsonify(
        chats=chats,
        files=[{**f.to_dict(), "snippet": _snippet(f.extracted_text or "", q) if q.lower() not in f.name.lower() else ""} for f in files],
        generated=[{**_library_item_gen(g)} for g in gens],
    )


# ------------------------------------------------------------------ settings & account
@bp.get("/settings")
@api_login_required
def get_settings():
    return jsonify(settings=settings_for(current_user).to_dict(), user=current_user.to_dict())


@bp.patch("/settings")
@api_login_required
def update_settings():
    s = settings_for(current_user)
    data = body()
    choices = {"theme": {"light", "dark", "system"}, "response_style": {"concise", "balanced", "detailed"},
               "font_size": {"sm", "md", "lg"}, "accent": {"cybok", "blue", "red", "violet", "emerald"}}
    for k, allowed in choices.items():
        if k in data and data[k] in allowed:
            setattr(s, k, data[k])
    for k in ("enter_to_send", "save_history", "email_notifications", "system_notifications", "voice_autospeak"):
        if k in data:
            setattr(s, k, bool(data[k]))
    if "custom_instructions" in data:
        s.custom_instructions = clean_text(data["custom_instructions"], 3000)
    if "voice_name" in data:
        s.voice_name = clean_text(data["voice_name"], 120)
    if "voice_rate" in data:
        try:
            s.voice_rate = max(0.5, min(2.0, float(data["voice_rate"])))
        except (TypeError, ValueError):
            pass
    if "default_model" in data:
        m = get_model(data["default_model"])
        s.default_model = m.slug if m else None
    db.session.commit()
    return ok(settings=s.to_dict())


@bp.patch("/profile")
@api_login_required
def update_profile():
    data = body()
    u = current_user
    if "name" in data:
        name = clean_text(data["name"], 120)
        if len(name) < 2:
            return err("Name is too short.")
        u.name = name
    if "email" in data:
        email = clean_text(data["email"], 255).lower()
        if email != u.email:
            if not valid_email(email):
                return err("Enter a valid e-mail address.")
            if u.password_hash and not u.check_password(data.get("password") or ""):
                return err("Enter your current password to change your e-mail.")
            if User.query.filter(User.email == email, User.id != u.id).first():
                return err("That e-mail is already used by another account.")
            old = u.email
            u.email = email
            if u.settings and u.settings.email_notifications:
                send_mail(old, "Your Cybok e-mail was changed", f"Hi {u.name},\n\nYour Cybok sign-in e-mail was changed to {email}.\nIf this wasn't you, reset your password immediately.\n\n- Cybok")
    db.session.commit()
    return ok(user=u.to_dict())


@bp.post("/profile/avatar")
@api_login_required
@rate_limit("upload", "RATE_UPLOAD_PER_MIN")
def upload_avatar():
    storage = request.files.get("file")
    if not storage:
        return err("No image received.")
    data = storage.read(5 * 1024 * 1024 + 1)
    if len(data) > 5 * 1024 * 1024:
        return err("Profile pictures must be under 5 MB.")
    try:
        with Image.open(io.BytesIO(data)) as im:
            im = im.convert("RGB")
            side = min(im.size)
            left, top = (im.width - side) // 2, (im.height - side) // 2
            im = im.crop((left, top, left + side, top + side)).resize((256, 256), Image.LANCZOS)
            buf = io.BytesIO()
            im.save(buf, "WEBP", quality=88)
    except Exception:
        return err("That file isn't a supported image.")
    from ..models import new_id
    rel = f"{current_user.id}/avatar-{new_id()[:12]}.webp"
    path = abs_path(rel)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(buf.getvalue())
    old = current_user.avatar
    current_user.avatar = rel
    db.session.commit()
    if old and not old.startswith("http"):
        try:
            abs_path(old).unlink(missing_ok=True)
        except Exception:
            pass
    return ok(user=current_user.to_dict())


@bp.delete("/profile/avatar")
@api_login_required
def delete_avatar():
    old = current_user.avatar
    current_user.avatar = None
    db.session.commit()
    if old and not old.startswith("http"):
        try:
            abs_path(old).unlink(missing_ok=True)
        except Exception:
            pass
    return ok(user=current_user.to_dict())


@bp.post("/profile/password")
@api_login_required
@rate_limit("auth", "RATE_AUTH_PER_5MIN", window=300)
def change_password():
    data = body()
    u = current_user
    if u.password_hash and not u.check_password(data.get("current") or ""):
        return err("Your current password is incorrect.")
    problem = password_problem(data.get("new") or "")
    if problem:
        return err(problem)
    u.set_password(data["new"])
    u.session_version += 1  # signs out other devices
    db.session.commit()
    from flask_login import login_user
    login_user(u, remember=True)  # keep this device signed in with the new session version
    if u.settings and u.settings.email_notifications:
        send_mail(u.email, "Your Cybok password was changed",
                  f"Hi {u.name},\n\nYour Cybok password was just changed. If this wasn't you, reset it immediately.\n\n- Cybok")
    return ok()


@bp.get("/account/export")
@api_login_required
def export_account():
    u = current_user
    convs = Conversation.query.filter_by(user_id=u.id).all()
    data = {
        "exported_at": iso(utcnow()), "user": u.to_dict(), "settings": settings_for(u).to_dict(),
        "conversations": [{**c.to_dict(), "messages": [m.to_dict() for m in c.messages]} for c in convs],
        "files": [f.to_dict() for f in File.query.filter_by(user_id=u.id)],
        "generated": [g.to_dict() | {"output": g.output} for g in GeneratedContent.query.filter_by(user_id=u.id)],
    }
    return Response(json.dumps(data, indent=2, ensure_ascii=False), mimetype="application/json",
                    headers={"Content-Disposition": 'attachment; filename="cybok-export.json"'})


@bp.post("/account/delete")
@api_login_required
@rate_limit("auth", "RATE_AUTH_PER_5MIN", window=300)
def delete_account():
    data = body()
    u = current_user
    if u.password_hash:
        if not u.check_password(data.get("password") or ""):
            return err("Password is incorrect.")
    elif (data.get("confirm") or "").strip().upper() != "DELETE":
        return err('Type DELETE to confirm.')
    if u.is_admin and User.query.filter_by(role="admin").count() == 1 and User.query.count() > 1:
        return err("You are the only administrator. Make someone else an admin first.")
    delete_user_data(u)
    from flask import session
    session.clear()
    logout_user()
    return ok()


def delete_user_data(u):
    import shutil
    for f in File.query.filter_by(user_id=u.id).all():
        delete_file_blob(f)
    try:
        shutil.rmtree(abs_path(str(u.id)), ignore_errors=True)
    except Exception:
        pass
    GeneratedContent.query.filter_by(user_id=u.id).delete()
    File.query.filter_by(user_id=u.id).delete()
    for c in Conversation.query.filter_by(user_id=u.id).all():
        db.session.delete(c)
    db.session.delete(u)
    db.session.commit()
