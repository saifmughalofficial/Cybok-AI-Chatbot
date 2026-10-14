"""Business logic used by the Streamlit UI. Every function takes the signed-in user and scopes queries to it."""
import base64
import io
import json
import os
import re
import shutil
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta

from flask import current_app
from PIL import Image
from sqlalchemy import func, or_

from .ai import images as image_ai
from .ai import logos as logo_ai
from .ai.chat import (FREE_KEYS, ProviderError, _local_cache, complete, fallback_models, get_model, is_available,
                      model_public, resolve_key, stream_chat)
from .ai.images import PROVIDERS as IMAGE_PROVIDERS
from .appsettings import get_setting, set_setting, setting_bool
from .extensions import db
from .files import UploadError, abs_path, delete_file_blob, handle_upload, safe_display_name, save_bytes, storage_root
from .identity import identity_reply, system_prompt
from .mailer import send_mail
from .models import (AIModel, Announcement, Conversation, ErrorLog, File, GeneratedContent, Message, UsageEvent, User,
                     UserSettings, iso, new_id, utcnow)
from .security import clean_text, log_error, log_usage, password_problem, rate_problem, valid_email

MAX_ATTACHMENTS = 8
THINK_RE = re.compile(r"<think>.*?</think>\s*", re.S)


class ServiceError(Exception):
    pass


def cfg(key):
    return current_app.config[key]


# ------------------------------------------------------------------ auth
def registration_open():
    return setting_bool("registration_open") or not User.query.count()


def _finish_login(user):
    if not user.settings:
        user.settings = UserSettings()
    # Bootstrap: the first account, or any e-mail in ADMIN_EMAILS, becomes an admin.
    if user.role != "admin" and (user.email.lower() in cfg("ADMIN_EMAILS") or
                                 not User.query.filter_by(role="admin").count()):
        user.role = "admin"
    user.last_seen_at = utcnow()
    db.session.commit()
    return user


def login(email, password):
    email = clean_text(email, 255).lower()
    if rate_problem("auth", email, cfg("RATE_AUTH_PER_5MIN"), 300):
        raise ServiceError("Too many attempts. Please wait a few minutes.")
    user = User.query.filter_by(email=email).first()
    if not user or not user.check_password(password or ""):
        raise ServiceError("Incorrect e-mail or password.")
    if user.disabled:
        raise ServiceError("This account has been disabled. Contact the administrator.")
    return _finish_login(user)


def signup(name, email, password, password2, accept_terms):
    if not registration_open():
        raise ServiceError("New registrations are currently closed.")
    name, email = clean_text(name, 120), clean_text(email, 255).lower()
    if len(name) < 2:
        raise ServiceError("Please enter your name.")
    if not valid_email(email):
        raise ServiceError("Enter a valid e-mail address.")
    problem = password_problem(password)
    if problem:
        raise ServiceError(problem)
    if password != password2:
        raise ServiceError("Passwords don't match.")
    if not accept_terms:
        raise ServiceError("Please accept the terms to continue.")
    if User.query.filter_by(email=email).first():
        raise ServiceError("An account with this e-mail already exists. Sign in instead.")
    user = User(name=name, email=email)
    user.set_password(password)
    db.session.add(user)
    db.session.flush()
    return _finish_login(user)


def _reset_serializer():
    from itsdangerous import URLSafeTimedSerializer
    return URLSafeTimedSerializer(cfg("SECRET_KEY"), salt="cybok-password-reset")


def forgot_password(email, base_url):
    """E-mails a reset link (printed to the console when SMTP isn't configured)."""
    email = clean_text(email, 255).lower()
    if rate_problem("auth", email, cfg("RATE_AUTH_PER_5MIN"), 300):
        raise ServiceError("Too many attempts. Please wait a few minutes.")
    user = User.query.filter_by(email=email).first()
    if user and not user.disabled:
        token = _reset_serializer().dumps({"uid": user.id, "v": user.session_version,
                                           "h": (user.password_hash or "")[-12:]})
        link = f"{(cfg('PUBLIC_URL') or base_url).rstrip('/')}/?reset={token}"
        send_mail(user.email, "Reset your Cybok password",
                  f"Hi {user.name},\n\nUse this link to set a new Cybok password (valid for 1 hour):\n{link}\n\n"
                  "If you didn't ask for this, you can ignore this e-mail.\n\n- Cybok")


def reset_password(token, password, password2):
    from itsdangerous import BadSignature, SignatureExpired
    try:
        data = _reset_serializer().loads(token, max_age=3600)
    except SignatureExpired:
        raise ServiceError("This reset link has expired. Please request a new one.")
    except BadSignature:
        raise ServiceError("This reset link is invalid.")
    user = db.session.get(User, data.get("uid"))
    if not user or user.session_version != data.get("v") or (user.password_hash or "")[-12:] != data.get("h"):
        raise ServiceError("This reset link was already used or is no longer valid.")
    problem = password_problem(password or "")
    if problem:
        raise ServiceError(problem)
    if password != password2:
        raise ServiceError("Passwords don't match.")
    user.set_password(password)
    user.session_version += 1  # sign out everywhere
    db.session.commit()


def load_user(uid, version):
    u = db.session.get(User, uid) if uid else None
    if u and u.session_version == version and not u.disabled:
        return u
    return None


def settings_for(user):
    if not user.settings:
        user.settings = UserSettings()
        db.session.commit()
    return user.settings


def max_upload_mb():
    try:
        return max(1, min(200, int(get_setting("max_upload_mb") or cfg("MAX_UPLOAD_MB"))))
    except ValueError:
        return cfg("MAX_UPLOAD_MB")


# ------------------------------------------------------------------ conversations
def heuristic_title(text):
    t = re.sub(r"[`*_#>\[\]()!]+", "", text or "").strip().splitlines()
    t = (t[0] if t else "").strip()
    if not t:
        return "New chat"
    if len(t) <= 52:
        return t[0].upper() + t[1:]
    cut = t[:52].rsplit(" ", 1)[0]
    return (cut or t[:52]).rstrip(",.;:") + "…"


def purge_old(user):
    """House-keeping: trash older than 30 days and stale temporary chats are removed."""
    cutoff = utcnow() - timedelta(days=30)
    Conversation.query.filter(Conversation.user_id == user.id, Conversation.deleted_at.isnot(None),
                              Conversation.deleted_at < cutoff).delete(synchronize_session=False)
    Conversation.query.filter(Conversation.user_id == user.id, Conversation.temporary.is_(True),
                              Conversation.updated_at < utcnow() - timedelta(hours=12)).delete(synchronize_session=False)
    user.last_seen_at = utcnow()
    db.session.commit()


def list_chats(user, view="active"):
    q = Conversation.query.filter_by(user_id=user.id, temporary=False)
    if view == "trash":
        q = q.filter(Conversation.deleted_at.isnot(None))
    else:
        q = q.filter(Conversation.deleted_at.is_(None)).filter_by(archived=view == "archived")
    return q.order_by(Conversation.pinned.desc(), Conversation.updated_at.desc()).limit(500).all()


def own_conv(user, cid, include_deleted=False):
    q = Conversation.query.filter_by(id=cid, user_id=user.id)
    if not include_deleted:
        q = q.filter(Conversation.deleted_at.is_(None))
    return q.first()


def create_chat(user, model_slug=None, temporary=False):
    s = settings_for(user)
    m = get_model(model_slug or s.default_model)
    conv = Conversation(user_id=user.id, model=m.slug if m else None, temporary=temporary or not s.save_history)
    db.session.add(conv)
    db.session.commit()
    return conv


def update_chat(conv, **data):
    if "title" in data:
        conv.title = clean_text(data["title"], 200) or "New chat"
    if "pinned" in data:
        conv.pinned = bool(data["pinned"])
    if "archived" in data:
        conv.archived = bool(data["archived"])
        if conv.archived:
            conv.pinned = False
    db.session.commit()


def delete_chat(conv, permanent=False):
    if permanent or conv.deleted_at is not None or conv.temporary:
        db.session.delete(conv)
    else:
        conv.deleted_at = utcnow()
        conv.pinned = False
        conv.share_enabled = False
    db.session.commit()


def restore_chat(conv):
    conv.deleted_at = None
    db.session.commit()


def empty_trash(user):
    for c in Conversation.query.filter_by(user_id=user.id).filter(Conversation.deleted_at.isnot(None)).all():
        db.session.delete(c)
    db.session.commit()


def set_share(conv, enabled, regenerate=False):
    if regenerate:
        conv.share_token = None
    if enabled:
        conv.ensure_share_token()
        conv.share_enabled = True
        conv.shared_at = utcnow()
        conv.temporary = False
    else:
        conv.share_enabled = False
    db.session.commit()


def shared_conv(token):
    if not token:
        return None
    return Conversation.query.filter_by(share_token=token, share_enabled=True).filter(
        Conversation.deleted_at.is_(None)).first()


def export_chat(conv):
    lines = [f"# {conv.title}", "", f"_Exported from Cybok — {utcnow():%Y-%m-%d %H:%M} UTC_", ""]
    for m in conv.messages:
        who = "You" if m.role == "user" else "Cybok"
        lines += [f"### {who}", "", m.content or "", ""]
    name = re.sub(r"[^A-Za-z0-9 _-]", "", conv.title)[:60].strip() or "chat"
    return "\n".join(lines), f"{name}.md"


def files_by_id(user_id, ids):
    if not ids:
        return {}
    rows = File.query.filter(File.id.in_(ids), File.user_id == user_id).all()
    return {f.id: f for f in rows}


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
    fmap = files_by_id(conv.user_id, all_ids)
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
            text = THINK_RE.sub("", text)
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


def prepare_turn(user, conv, model_slug, mode="send", content="", attachments=(), message_id=None):
    """Stores the user message + an empty assistant message. Returns a dict the streamer needs."""
    problem = rate_problem("chat", user.id, cfg("RATE_CHAT_PER_MIN"))
    if problem:
        raise ServiceError(problem)
    s = settings_for(user)
    model = get_model(model_slug or conv.model or s.default_model)
    if model is None:
        raise ServiceError("No AI model is ready yet. An admin can turn one on for free in Admin › System "
                           "(paste a free Groq key) or by installing Ollama - see the user manual.")
    if mode == "regenerate":
        user_msg = conv.messages.filter_by(role="user").order_by(Message.id.desc()).first()
        if not user_msg:
            raise ServiceError("Nothing to regenerate.")
        Message.query.filter(Message.conversation_id == conv.id, Message.id > user_msg.id).delete(synchronize_session=False)
    elif mode == "edit":
        user_msg = conv.messages.filter_by(id=message_id, role="user").first()
        content = clean_text(content, 60000)
        if not user_msg or not content:
            raise ServiceError("Message can't be empty.")
        user_msg.content = content
        Message.query.filter(Message.conversation_id == conv.id, Message.id > user_msg.id).delete(synchronize_session=False)
    else:
        content = clean_text(content, 60000)
        att = [str(a) for a in attachments][:MAX_ATTACHMENTS]
        fmap = files_by_id(user.id, att)
        att = [a for a in att if a in fmap]
        if not content and not att:
            raise ServiceError("Type a message or attach a file.")
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
    has_images = any(f.kind == "image" for f in files_by_id(user.id, user_msg.attachment_ids).values())
    return {"conv_id": conv.id, "model_slug": model.slug, "user_msg_id": user_msg.id, "asst_id": assistant.id,
            "user_text": user_msg.content or "", "first_turn": first_turn, "has_images": has_images,
            "user_id": user.id, "notices": []}


def stream_turn(turn):
    """Generator of text chunks for the assistant answer; saves the result when finished."""
    conv = db.session.get(Conversation, turn["conv_id"])
    s = settings_for(db.session.get(User, turn["user_id"]))
    model = AIModel.query.filter_by(slug=turn["model_slug"]).first()
    used, parts, status, error = model, [], "done", None
    fixed = identity_reply(turn["user_text"])
    try:
        if fixed:
            for word in re.findall(r"\S+\s*", fixed):
                parts.append(word)
                yield word
                time.sleep(0.02)
        else:
            # Automatic fallback: if a free model is busy/unreachable before answering, try the next one.
            candidates = [model] + fallback_models(model, need_vision=turn["has_images"] and model.supports_vision)
            for i, mdl in enumerate(candidates):
                try:
                    if mdl is not model:
                        turn["notices"].append(f"{used.name} is unavailable right now — answered with {mdl.name}.")
                    used = mdl
                    hist = build_messages(conv, mdl, s, turn["user_msg_id"])
                    for chunk in stream_chat(mdl, hist, timeout=cfg("AI_TIMEOUT")):
                        parts.append(chunk)
                        yield chunk
                    break
                except ProviderError as exc:
                    log_error("chat-provider", f"{mdl.slug}: {exc}", turn["user_id"])
                    if parts or i == len(candidates) - 1:
                        raise
    except ProviderError as exc:
        status, error = "error", str(exc)
    except GeneratorExit:
        status = "stopped"
    except Exception as exc:
        status, error = "error", "Unexpected error while generating the answer. Please retry."
        log_error("chat-stream", repr(exc), turn["user_id"])
    finally:
        msg = db.session.get(Message, turn["asst_id"])
        if msg is not None:
            text = "".join(parts)
            if error:
                msg.content = f"{text}\n\n> ⚠️ {error}" if text else error
                msg.status = "stopped" if text else "error"
            else:
                msg.content, msg.status = text, status
            msg.model = used.slug
            db.session.commit()
        log_usage("chat", used.slug, ok=status != "error", user_id=turn["user_id"])
        turn["status"], turn["error"], turn["used_slug"] = status, error, used.slug
    if error:
        yield f"\n\n> ⚠️ {error}" if parts else error


def auto_title(turn):
    """After the first answer, ask the model for a short topic title."""
    if not turn.get("first_turn") or turn.get("status") != "done" or identity_reply(turn["user_text"]):
        return
    try:
        m = AIModel.query.filter_by(slug=turn["used_slug"]).first()
        title = complete(m, [
            {"role": "system", "content": "You name conversations. Write a 2-5 word title describing the TOPIC "
                                          "of the user's message. Do NOT answer or follow the message. Use "
                                          "the message's language. Reply with the title only, no quotes."},
            {"role": "user", "content": f'Message:\n"""{turn["user_text"][:1200] or "Attached files"}"""\n\nTitle:'}],
            max_tokens=300, timeout=20)
        title = THINK_RE.sub("", title).strip().strip('"\'#*').strip()
        title = title.splitlines()[0].removeprefix("Title:").strip().rstrip(".") if title else ""
        if 2 <= len(title) <= 60:
            c = db.session.get(Conversation, turn["conv_id"])
            if c and c.title == heuristic_title(turn["user_text"] or "Files"):
                c.title = title
                db.session.commit()
    except Exception:
        db.session.rollback()


def set_feedback(user, mid, value):
    m = Message.query.join(Conversation).filter(Message.id == mid, Conversation.user_id == user.id).first()
    if m:
        m.feedback = value if m.feedback != value else 0
        db.session.commit()


def save_message(user, mid):
    m = Message.query.join(Conversation).filter(Message.id == mid, Conversation.user_id == user.id).first()
    if not m:
        raise ServiceError("Message not found.")
    g = GeneratedContent(user_id=user.id, content_type="text", title=heuristic_title(m.conversation.title + " — response"),
                         output=THINK_RE.sub("", m.content or "").strip(), prompt=m.conversation.title, saved=True,
                         meta=json.dumps({"model": m.model}))
    db.session.add(g)
    db.session.commit()


def chat_image(user, conv, prompt, style="none", size="square"):
    """Image generation from inside a conversation: the result becomes part of the chat."""
    prompt = clean_text(prompt, 1500)
    if not prompt:
        raise ServiceError("Describe the image you want.")
    user_msg = Message(conversation_id=conv.id, role="user", content=f"\U0001f3a8 Create image: {prompt}")
    db.session.add(user_msg)
    if conv.title == "New chat":
        conv.title = heuristic_title("Image: " + prompt)
    db.session.commit()
    try:
        g = generate_images(user, prompt, style, size, 1, "image")[0]
        meta = json.loads(g.meta or "{}")
        content = (f"Here's your image — *{prompt}*\n\n![{prompt.replace(']', '')}](/media/file/{g.file_id})\n\n"
                   f"<sub>Generated with {meta.get('provider', 'image model')} · style: "
                   f"{image_ai.STYLES[style][0]} · seed {meta.get('seed')}</sub>")
        a = Message(conversation_id=conv.id, role="assistant", model="image", content=content)
    except (image_ai.ImageError, ServiceError) as exc:
        a = Message(conversation_id=conv.id, role="assistant", content=f"⚠️ {exc}", status="error", model="image")
    db.session.add(a)
    conv.updated_at = utcnow()
    db.session.commit()


# ------------------------------------------------------------------ images & logos
def generate_images(user, prompt, style, size, count, content_type, extra_meta=None, prompts=None, seeds=None):
    problem = rate_problem("image", user.id, cfg("RATE_IMAGE_PER_MIN"))
    if problem:
        raise ServiceError(problem)
    conf = image_ai.image_config()
    prompts = prompts or [prompt] * count
    seeds = seeds or [None] * len(prompts)
    # The keyless image tier allows one request at a time, so generate sequentially unless a token is set.
    keyless = conf.get("image_provider", "pollinations") == "pollinations" and not conf.get("pollinations_token")
    with ThreadPoolExecutor(max_workers=1 if keyless else min(4, len(prompts))) as pool:
        futures = [pool.submit(image_ai.generate, p, conf, style, size, sd) for p, sd in zip(prompts, seeds)]
        results, errors = [], []
        for fut in futures:
            try:
                results.append(fut.result())
            except image_ai.ImageError as exc:
                errors.append(str(exc))
                log_error("image", str(exc), user.id)
            except Exception as exc:
                errors.append("Image generation failed.")
                log_error("image", repr(exc), user.id)
    if not results:
        log_usage(content_type, conf.get("image_provider"), ok=False, user_id=user.id)
        raise image_ai.ImageError(errors[0] if errors else "Image generation failed.")
    items = []
    for data, mime, label, seed in results:
        ext = {"image/png": "png", "image/webp": "webp"}.get(mime, "jpg")
        name = safe_display_name(re.sub(r"\s+", "-", prompt[:40]).strip("-") or "image") + f".{ext}"
        f = save_bytes(user.id, data, name, mime=mime, source="generated", in_library=False)
        meta = {"provider": label, "seed": seed, "size": size, **(extra_meta or {})}
        g = GeneratedContent(user_id=user.id, content_type=content_type, title=prompt[:120], prompt=prompt,
                             file_id=f.id, style=style, meta=json.dumps(meta), saved=False)
        db.session.add(g)
        items.append(g)
        log_usage(content_type, label, user_id=user.id)
    db.session.commit()
    return items


def create_logos(user, ai_count=0, **fields):
    fields = {k: clean_text(fields.get(k), 120) for k in ("brand", "industry", "style", "colors", "symbol", "typography")}
    if not fields["brand"]:
        raise ServiceError("Enter a brand name.")
    batch = logo_ai.svg_fingerprint(json.dumps(fields) + str(time.time()))
    items = []
    for concept in logo_ai.generate_concepts(**fields):
        g = GeneratedContent(user_id=user.id, content_type="logo", title=f"{fields['brand']} — {concept['title']}",
                             prompt=json.dumps(fields), output=concept["svg"], style="vector",
                             meta=json.dumps({"kind": "vector", "concept": concept["title"], "batch": batch, **fields}))
        db.session.add(g)
        items.append(g)
    db.session.commit()
    log_usage("logo", "vector", user_id=user.id)
    ai_error = None
    if ai_count:
        prompts = [logo_ai.ai_logo_prompt(variant=i, **fields) for i in range(ai_count)]
        try:
            ai_items = generate_images(user, fields["brand"], "none", "square", ai_count, "logo", prompts=prompts,
                                       extra_meta={"kind": "ai", "batch": batch, **fields})
            for g in ai_items:
                g.title = f"{fields['brand']} — AI concept"
            db.session.commit()
            items = ai_items + items
        except (image_ai.ImageError, ServiceError) as exc:
            ai_error = str(exc)
    return items, ai_error


def list_generated(user, ctype, limit=60):
    q = GeneratedContent.query.filter_by(user_id=user.id)
    if ctype != "all":
        q = q.filter_by(content_type=ctype)
    return q.order_by(GeneratedContent.created_at.desc()).limit(limit).all()


def own_generated(user, gid):
    return GeneratedContent.query.filter_by(id=gid, user_id=user.id).first()


def toggle_saved(g):
    g.saved = not g.saved
    if g.file:
        g.file.in_library = False  # the generated item itself represents it in the Library
    db.session.commit()


def delete_generated(g):
    f = g.file
    db.session.delete(g)
    if f:
        delete_file_blob(f)
        db.session.delete(f)
    db.session.commit()


# ------------------------------------------------------------------ files & library
def upload(user, filename, data):
    problem = rate_problem("upload", user.id, cfg("RATE_UPLOAD_PER_MIN"))
    if problem:
        raise ServiceError(problem)
    try:
        f = handle_upload(user.id, filename, data, max_upload_mb())
        db.session.commit()
    except UploadError as exc:
        db.session.rollback()
        raise ServiceError(str(exc))
    log_usage("upload", f.ext, user_id=user.id)
    return f


def library(user, t="all", q="", folder="__all__", sort="new"):
    """Returns (items, folders, storage_used). Items: (kind, obj) with kind 'file' or 'gen'."""
    items = []
    if t in ("all", "document", "data", "code", "image"):
        fq = File.query.filter_by(user_id=user.id, source="upload", in_library=True)
        if t != "all":
            fq = fq.filter_by(kind=t)
        items += [("file", f) for f in fq.limit(2000)]
    if t in ("all", "image", "logo", "text"):
        gq = GeneratedContent.query.filter_by(user_id=user.id, saved=True)
        if t != "all":
            gq = gq.filter_by(content_type=t)
        items += [("gen", g) for g in gq.limit(2000)]
    title = lambda it: (it[1].name if it[0] == "file" else it[1].title) or ""
    size = lambda it: it[1].size if it[0] == "file" else (it[1].file.size if it[1].file else len(it[1].output or ""))
    if folder != "__all__":
        items = [i for i in items if (i[1].folder or "") == folder]
    q = (q or "").strip().lower()
    if q:
        items = [i for i in items if q in title(i).lower() or (i[0] == "gen" and (
            q in (i[1].prompt or "").lower() or q in (i[1].output or "").lower()[:5000]))]
    if sort == "name":
        items.sort(key=lambda i: title(i).lower())
    elif sort == "size":
        items.sort(key=size, reverse=True)
    else:
        items.sort(key=lambda i: i[1].created_at, reverse=sort != "old")
    folders = sorted({f.folder for f in File.query.filter_by(user_id=user.id).all() if f.folder} |
                     {g.folder for g in GeneratedContent.query.filter_by(user_id=user.id, saved=True).all() if g.folder})
    used = sum(f.size or 0 for f in File.query.filter_by(user_id=user.id).all())
    return items, folders, used


def rename_item(kind, obj, title, folder):
    title = clean_text(title, 200)
    if title:
        if kind == "file":
            ext = obj.ext
            obj.name = safe_display_name(title if not ext or title.lower().endswith("." + ext) else f"{title}.{ext}")
        else:
            obj.title = title
    obj.folder = clean_text(folder, 80)
    db.session.commit()


def delete_item(kind, obj):
    if kind == "file":
        delete_file_blob(obj)
        GeneratedContent.query.filter_by(file_id=obj.id).delete()
        db.session.delete(obj)
        db.session.commit()
    else:
        delete_generated(obj)


def search(user, q):
    q = clean_text(q, 100)
    if len(q) < 2:
        return [], [], []
    like = f"%{q.replace('%', '').replace('_', '')}%"
    base = Conversation.query.filter_by(user_id=user.id, temporary=False).filter(Conversation.deleted_at.is_(None))
    chats = [(c, "") for c in base.filter(Conversation.title.ilike(like)).order_by(Conversation.updated_at.desc()).limit(10)]
    seen = {c.id for c, _ in chats}
    msg_hits = (db.session.query(Message, Conversation).join(Conversation)
                .filter(Conversation.user_id == user.id, Conversation.temporary.is_(False),
                        Conversation.deleted_at.is_(None), Message.content.ilike(like))
                .order_by(Message.id.desc()).limit(40).all())
    for m, c in msg_hits:
        if c.id not in seen and len(chats) < 15:
            seen.add(c.id)
            chats.append((c, _snippet(m.content, q)))
    files = File.query.filter(File.user_id == user.id, File.source == "upload",
                              or_(File.name.ilike(like), File.extracted_text.ilike(like))).limit(10).all()
    gens = GeneratedContent.query.filter(GeneratedContent.user_id == user.id,
                                         or_(GeneratedContent.title.ilike(like), GeneratedContent.prompt.ilike(like),
                                             GeneratedContent.output.ilike(like) & (GeneratedContent.content_type == "text"))
                                         ).order_by(GeneratedContent.created_at.desc()).limit(10).all()
    return chats, files, gens


def _snippet(text, q, width=90):
    if not text:
        return ""
    i = text.lower().find(q.lower())
    if i < 0:
        return text[:width * 2].replace("\n", " ")
    start = max(0, i - width)
    return ("…" if start else "") + text[start:i + len(q) + width].replace("\n", " ") + "…"


# ------------------------------------------------------------------ settings & account
def update_settings(user, **data):
    s = settings_for(user)
    for k in ("theme", "response_style", "font_size", "accent", "enter_to_send", "save_history",
              "email_notifications", "voice_autospeak"):
        if k in data:
            setattr(s, k, data[k])
    if "custom_instructions" in data:
        s.custom_instructions = clean_text(data["custom_instructions"], 3000)
    if "default_model" in data:
        m = get_model(data["default_model"])
        s.default_model = m.slug if m else None
    db.session.commit()


def update_profile(user, name, email, password=""):
    name = clean_text(name, 120)
    if len(name) < 2:
        raise ServiceError("Name is too short.")
    user.name = name
    email = clean_text(email, 255).lower()
    if email != user.email:
        if not valid_email(email):
            raise ServiceError("Enter a valid e-mail address.")
        if user.password_hash and not user.check_password(password or ""):
            raise ServiceError("Enter your current password to change your e-mail.")
        if User.query.filter(User.email == email, User.id != user.id).first():
            raise ServiceError("That e-mail is already used by another account.")
        old, user.email = user.email, email
        if user.settings and user.settings.email_notifications:
            send_mail(old, "Your Cybok e-mail was changed", f"Hi {user.name},\n\nYour Cybok sign-in e-mail was changed "
                      f"to {email}.\nIf this wasn't you, reset your password immediately.\n\n- Cybok")
    db.session.commit()


def set_avatar(user, data):
    if len(data) > 5 * 1024 * 1024:
        raise ServiceError("Profile pictures must be under 5 MB.")
    try:
        with Image.open(io.BytesIO(data)) as im:
            im = im.convert("RGB")
            side = min(im.size)
            left, top = (im.width - side) // 2, (im.height - side) // 2
            im = im.crop((left, top, left + side, top + side)).resize((256, 256), Image.LANCZOS)
            buf = io.BytesIO()
            im.save(buf, "WEBP", quality=88)
    except Exception:
        raise ServiceError("That file isn't a supported image.")
    rel = f"{user.id}/avatar-{new_id()[:12]}.webp"
    path = abs_path(rel)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(buf.getvalue())
    old, user.avatar = user.avatar, rel
    db.session.commit()
    if old and not old.startswith("http"):
        abs_path(old).unlink(missing_ok=True)


def avatar_path(user):
    if user.avatar and not user.avatar.startswith("http"):
        p = abs_path(user.avatar)
        return str(p) if p.exists() else None
    return user.avatar


def change_password(user, current, new, new2):
    if user.password_hash and not user.check_password(current or ""):
        raise ServiceError("Your current password is incorrect.")
    problem = password_problem(new or "")
    if problem:
        raise ServiceError(problem)
    if new != new2:
        raise ServiceError("Passwords don't match.")
    user.set_password(new)
    user.session_version += 1  # signs out other devices
    db.session.commit()
    if user.settings and user.settings.email_notifications:
        send_mail(user.email, "Your Cybok password was changed",
                  f"Hi {user.name},\n\nYour Cybok password was just changed. If this wasn't you, reset it immediately.\n\n- Cybok")


def export_account(user):
    convs = Conversation.query.filter_by(user_id=user.id).all()
    data = {
        "exported_at": iso(utcnow()), "user": user.to_dict(), "settings": settings_for(user).to_dict(),
        "conversations": [{**c.to_dict(), "messages": [m.to_dict() for m in c.messages]} for c in convs],
        "files": [f.to_dict() for f in File.query.filter_by(user_id=user.id)],
        "generated": [g.to_dict() | {"output": g.output} for g in GeneratedContent.query.filter_by(user_id=user.id)],
    }
    return json.dumps(data, indent=2, ensure_ascii=False)


def delete_account(user, password="", confirm=""):
    if user.password_hash:
        if not user.check_password(password or ""):
            raise ServiceError("Password is incorrect.")
    elif (confirm or "").strip().upper() != "DELETE":
        raise ServiceError("Type DELETE to confirm.")
    if user.is_admin and User.query.filter_by(role="admin").count() == 1 and User.query.count() > 1:
        raise ServiceError("You are the only administrator. Make someone else an admin first.")
    delete_user_data(user)


def delete_user_data(u):
    for f in File.query.filter_by(user_id=u.id).all():
        delete_file_blob(f)
    shutil.rmtree(abs_path(str(u.id)), ignore_errors=True)
    GeneratedContent.query.filter_by(user_id=u.id).delete()
    File.query.filter_by(user_id=u.id).delete()
    for c in Conversation.query.filter_by(user_id=u.id).all():
        db.session.delete(c)
    db.session.delete(u)
    db.session.commit()


def active_announcements():
    return Announcement.query.filter_by(active=True).order_by(Announcement.created_at.desc()).limit(3).all()


# ------------------------------------------------------------------ admin
def admin_stats():
    now = utcnow()
    day_ago, week_ago = now - timedelta(days=1), now - timedelta(days=7)
    count = lambda q: q.scalar() or 0
    usage = lambda kind: count(db.session.query(func.count(UsageEvent.id)).filter(UsageEvent.kind == kind))
    disk = 0
    for root, _, files in os.walk(storage_root()):
        disk += sum(os.path.getsize(os.path.join(root, f)) for f in files)
    start = (now - timedelta(days=13)).date()
    series = {(start + timedelta(days=i)).isoformat(): {"chat": 0, "image": 0, "logo": 0, "upload": 0} for i in range(14)}
    rows = (db.session.query(func.date(UsageEvent.created_at), UsageEvent.kind, func.count(UsageEvent.id))
            .filter(UsageEvent.created_at >= start).group_by(func.date(UsageEvent.created_at), UsageEvent.kind).all())
    for d, kind, n in rows:
        key = d if isinstance(d, str) else d.isoformat()
        if key in series and kind in series[key]:
            series[key][kind] = n
    names = {m.slug: m.name for m in AIModel.query.all()}
    model_rows = (db.session.query(UsageEvent.model, func.count(UsageEvent.id)).filter(UsageEvent.kind == "chat")
                  .group_by(UsageEvent.model).order_by(func.count(UsageEvent.id).desc()).limit(12).all())
    return {
        "Users": count(db.session.query(func.count(User.id))),
        "New this week": count(db.session.query(func.count(User.id)).filter(User.created_at >= week_ago)),
        "Active today": count(db.session.query(func.count(User.id)).filter(User.last_seen_at >= day_ago)),
        "Conversations": count(db.session.query(func.count(Conversation.id))),
        "Messages": count(db.session.query(func.count(Message.id))),
        "AI requests": usage("chat"),
        "AI failures": count(db.session.query(func.count(UsageEvent.id)).filter(
            UsageEvent.kind == "chat", UsageEvent.ok.is_(False))),
        "Images": usage("image"), "Logos": usage("logo"), "Uploads": usage("upload"),
        "Storage (MB)": round(disk / 1048576, 1),
        "Errors today": count(db.session.query(func.count(ErrorLog.id)).filter(ErrorLog.created_at >= day_ago)),
    }, series, [(names.get(m, m or "unknown"), n) for m, n in model_rows]


def admin_users(q=""):
    query = User.query
    if q:
        like = f"%{q}%"
        query = query.filter((User.name.ilike(like)) | (User.email.ilike(like)))
    return query.order_by(User.created_at.desc()).limit(500).all()


def admin_update_user(admin, uid, disabled=None, role=None):
    u = db.session.get(User, uid)
    if not u:
        raise ServiceError("User not found.")
    if u.id == admin.id and (disabled or role == "user"):
        raise ServiceError("You can't disable or demote your own account.")
    if disabled is not None and disabled != u.disabled:
        u.disabled = disabled
        u.session_version += 1  # kick active sessions
    if role in ("user", "admin"):
        u.role = role
    db.session.commit()


def admin_delete_user(admin, uid):
    u = db.session.get(User, uid)
    if u and u.id != admin.id:
        delete_user_data(u)


MODEL_FIELDS = {"slug": 80, "name": 120, "description": 300, "provider": 80, "model_family": 120, "api_base": 300,
                "api_model": 200, "api_key_env": 80, "badge": 30}


def save_model(m, data):
    """Create (m=None) or update an AI model row."""
    is_new = m is None
    m = m or AIModel()
    for f, n in MODEL_FIELDS.items():
        if f in data:
            setattr(m, f, clean_text(data[f], n))
    for f in ("key_required", "supports_vision", "supports_streaming", "enabled"):
        if f in data:
            setattr(m, f, bool(data[f]))
    for f, cast, lo, hi in (("temperature", float, 0, 2), ("max_tokens", int, 16, 64000),
                            ("context_chars", int, 2000, 500000), ("sort_order", int, 0, 10000)):
        if data.get(f) not in (None, ""):
            setattr(m, f, max(lo, min(hi, cast(data[f]))))
    if data.get("api_key"):
        m.api_key = clean_text(data["api_key"], 500)
    if not m.slug or not m.api_base or not m.api_model or not m.name:
        db.session.rollback()
        raise ServiceError("Name, slug, API base URL and API model are required.")
    if not m.api_base.startswith(("http://", "https://")):
        db.session.rollback()
        raise ServiceError("API base URL must start with http:// or https://")
    if AIModel.query.filter(AIModel.slug == m.slug, AIModel.id != (m.id or -1)).first():
        db.session.rollback()
        raise ServiceError("A model with this slug already exists.")
    if is_new:
        db.session.add(m)
    db.session.commit()
    return m


def test_model(m):
    if not is_available(m):
        return False, f"No API key. Set {m.api_key_env} in .env or paste a key in Free AI keys."
    try:
        reply = complete(m, [{"role": "user", "content": "Reply with exactly: Cybok test OK"}], max_tokens=400, timeout=40)
        return True, reply[:300] or "(empty reply - the model may only return reasoning)"
    except ProviderError as exc:
        return False, str(exc)


def key_status():
    out = []
    for name, (label, url) in FREE_KEYS.items():
        env_val = os.getenv(name, "").strip()
        db_val = get_setting(f"key:{name}").strip()
        val = env_val or db_val
        out.append({"name": name, "label": label, "url": url, "set": bool(val),
                    "source": "env" if env_val else ("admin" if db_val else None),
                    "hint": ("••••" + val[-4:]) if val else ""})
    return out


def save_keys(data):
    for name in FREE_KEYS:
        if data.get(name):
            set_setting(f"key:{name}", clean_text(data[name], 500))
    db.session.commit()
    _local_cache.clear()


def save_system_settings(data):
    raw = clean_text(data.get("creation_date"), 20)
    if raw:
        try:
            date.fromisoformat(raw)
        except ValueError:
            raise ServiceError("Creation date must be a valid date (YYYY-MM-DD).")
    set_setting("creation_date", raw)
    set_setting("registration_open", "1" if data.get("registration_open") else "0")
    set_setting("max_upload_mb", str(max(1, min(200, int(data.get("max_upload_mb") or 20)))))
    set_setting("system_prompt_extra", clean_text(data.get("system_prompt_extra"), 2000))
    if data.get("image_provider") in IMAGE_PROVIDERS:
        set_setting("image_provider", data["image_provider"])
    for k, n in (("image_model", 60), ("hf_image_model", 200), ("default_model", 80), ("maintenance_message", 300)):
        if k in data:
            set_setting(k, clean_text(data[k], n))
    db.session.commit()


def save_announcement(a, title, body, level, active):
    title = clean_text(title, 200)
    if not title:
        raise ServiceError("Title is required.")
    if a is None:
        a = Announcement()
        db.session.add(a)
    a.title, a.body = title, clean_text(body, 2000)
    a.level = level if level in ("info", "success", "warning") else "info"
    a.active = bool(active)
    db.session.commit()


def delete_row(row):
    db.session.delete(row)
    db.session.commit()


def clear_errors():
    ErrorLog.query.delete()
    db.session.commit()


def model_key_status(m):
    key = resolve_key(m)
    return "stored in model" if m.api_key else (f"from {m.api_key_env}" if key else "missing")
