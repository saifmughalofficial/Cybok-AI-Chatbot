"""Cybok - Your AI. Your Workspace.   Streamlit UI.

    streamlit run app.py        (or: python run.py)
"""
import json
import os
import re
import secrets
import time
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env", override=True)  # before importing cybok: Config reads the environment at import time
if not os.getenv("SECRET_KEY"):  # e.g. Streamlit Cloud without a SECRET_KEY secret: keep one in instance/
    _key_file = ROOT / "instance" / ".secret_key"
    _key_file.parent.mkdir(exist_ok=True)
    if not _key_file.exists():
        _key_file.write_text(secrets.token_urlsafe(48))
    os.environ["SECRET_KEY"] = _key_file.read_text().strip()

import pandas as pd  # noqa: E402
import requests  # noqa: E402
import streamlit as st  # noqa: E402
from itsdangerous import BadSignature, URLSafeTimedSerializer  # noqa: E402

from cybok import create_app  # noqa: E402
from cybok import services as sv  # noqa: E402
from cybok.ai import images as image_ai  # noqa: E402
from cybok.ai import video as video_ai  # noqa: E402
from cybok.ai.chat import (default_model_slug, enabled_models, get_secret, is_available,  # noqa: E402
                           unavailable_reason)
from cybok.appsettings import all_settings  # noqa: E402
from cybok.extensions import db  # noqa: E402
from cybok.files import ALLOWED_EXT, abs_path  # noqa: E402
from cybok.models import AIModel, Announcement, ErrorLog  # noqa: E402

IMG = ROOT / "cybok" / "static" / "img"
MARK = str(IMG / "mark.png")
COOKIE = "cybok_auth"
REMEMBER_DAYS = 30
MEDIA_RE = re.compile(r"!\[([^\]]*)\]\(/media/file/([0-9a-f]{32})\)")
THINK_RE = re.compile(r"<think>(.*?)(?:</think>|$)\s*", re.S)
SUB_RE = re.compile(r"<sub>(.*?)</sub>", re.S)
ss = st.session_state

st.set_page_config(page_title="Cybok", page_icon=str(IMG / "favicon.png"), layout="wide",
                   initial_sidebar_state="expanded")


@st.cache_resource
def flask_app():
    """Flask is only the container for Flask-SQLAlchemy (database session + config)."""
    return create_app()


# ------------------------------------------------------------------ styling
def css(font_size="md"):
    fs = {"sm": "14px", "md": "15.5px", "lg": "17.5px"}.get(font_size, "15.5px")
    st.markdown(f"""<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Michroma&display=swap');
html, body, .stApp, .stApp p, .stApp input, .stApp textarea, .stApp button, .stApp label {{
  font-family: "Inter", system-ui, sans-serif; }}
.cy-brand {{ font-family: "Michroma", sans-serif; font-size: 1.35rem; letter-spacing: .08em;
  background: linear-gradient(100deg,#ff4d5e 0%,#c25bff 45%,#3d82ff 90%); -webkit-background-clip: text;
  background-clip: text; color: transparent; margin: 0; }}
.cy-hero {{ font-family: "Michroma", sans-serif; font-size: clamp(1.6rem, 4vw, 2.6rem); line-height: 1.25;
  background: linear-gradient(100deg,#ff4d5e 0%,#c25bff 45%,#3d82ff 90%); -webkit-background-clip: text;
  background-clip: text; color: transparent; }}
.cy-tag {{ color: #a9aec6; margin-top: -.4rem; }}
[data-testid="stChatMessage"] {{ font-size: {fs}; }}
[data-testid="stChatMessage"] p {{ font-size: {fs}; }}
[data-testid="stSidebar"] [data-testid^="stBaseButton-"] {{ justify-content: flex-start; text-align: left;
  padding-left: .75rem; }}
[data-testid="stSidebar"] [data-testid="stBaseButton-tertiary"]:hover {{ background: rgba(77,132,255,.08); }}
[data-testid="stSidebar"] [data-testid^="stBaseButton-"] > div {{ justify-content: flex-start; width: 100%; }}
[data-testid="stSidebar"] [data-testid^="stBaseButton-"] p {{ white-space: nowrap; overflow: hidden;
  text-overflow: ellipsis; text-align: left; }}
[data-testid="stSidebar"] [data-testid="stBaseButton-primary"] {{ justify-content: center; padding-left: 0; }}
[data-testid="stSidebar"] [data-testid="stBaseButton-primary"] > div {{ justify-content: center; }}
.block-container {{ padding-top: 2.2rem; }}

/* ---- motion: short, eased, never in the way ---- */
@keyframes cyFadeUp {{ from {{ opacity: 0; transform: translateY(8px); }} to {{ opacity: 1; transform: none; }} }}
@keyframes cyFade {{ from {{ opacity: 0; }} to {{ opacity: 1; }} }}
@keyframes cyShift {{ 0%, 100% {{ background-position: 0% 50%; }} 50% {{ background-position: 100% 50%; }} }}
@keyframes cySweep {{ from {{ background-position: -200% 0; }} to {{ background-position: 200% 0; }} }}
@keyframes cyPulse {{ 0%, 100% {{ opacity: .55; }} 50% {{ opacity: 1; }} }}
.cy-hero, .cy-brand {{ background-size: 200% 200%; animation: cyShift 9s ease-in-out infinite; }}
.cy-hero {{ animation: cyShift 9s ease-in-out infinite, cyFadeUp .5s cubic-bezier(.22,.8,.24,1) both; }}
[data-testid="stChatMessage"] {{ animation: cyFadeUp .32s cubic-bezier(.22,.8,.24,1) both;
  border-radius: 14px; transition: background-color .2s ease; }}
[data-testid="stChatMessage"]:hover {{ background-color: rgba(77,132,255,.04); }}
.stButton > button, .stDownloadButton > button, .stFormSubmitButton > button, .stLinkButton > a {{
  border-radius: 10px; transition: transform .15s ease, box-shadow .2s ease, background-color .2s ease,
  border-color .2s ease; }}
.stButton > button:hover, .stDownloadButton > button:hover, .stFormSubmitButton > button:hover {{
  transform: translateY(-1px); box-shadow: 0 6px 18px -8px rgba(77,132,255,.55); }}
.stButton > button:active, .stFormSubmitButton > button:active {{ transform: translateY(0) scale(.98); }}
button[kind="primary"], button[kind="primaryFormSubmit"] {{
  background: linear-gradient(135deg,#ff3448 0%,#b03dff 48%,#2f73ff 100%) !important; background-size: 200% 200% !important;
  border: none !important; color: #fff !important; }}
button[kind="primary"]:hover, button[kind="primaryFormSubmit"]:hover {{ animation: cyShift 3s ease infinite; }}
[data-testid="stImage"] img, [data-testid="stVideo"] video {{ border-radius: 12px; animation: cyFade .45s ease both;
  transition: transform .25s cubic-bezier(.22,.8,.24,1), box-shadow .25s ease; }}
[data-testid="stColumn"] [data-testid="stImage"] img:hover {{ transform: translateY(-3px);
  box-shadow: 0 14px 34px -14px rgba(0,0,0,.7); }}
[data-testid="stExpander"], [data-testid="stForm"] {{ animation: cyFadeUp .3s ease both; border-radius: 12px; }}
[data-testid="stStatusWidget"], [data-testid="stSpinner"] {{ animation: cyPulse 1.6s ease-in-out infinite; }}
.cy-shimmer {{ border-radius: 14px; aspect-ratio: var(--ar, 1); width: 100%; margin: .25rem 0 1rem;
  background: linear-gradient(100deg, rgba(255,255,255,.03) 20%, rgba(194,91,255,.16) 40%, rgba(61,130,255,.16) 55%,
  rgba(255,255,255,.03) 75%); background-size: 200% 100%; animation: cySweep 1.6s linear infinite;
  border: 1px solid rgba(255,255,255,.06); }}
@media (prefers-reduced-motion: reduce) {{ *, *::before, *::after {{ animation: none !important;
  transition: none !important; }} }}
</style>""", unsafe_allow_html=True)


def shimmer(aspect="1", n=1):
    """Animated placeholder shown while media is being generated."""
    ph = st.empty()
    cols = ph.columns(n)
    for c in cols:
        c.markdown(f'<div class="cy-shimmer" style="--ar:{aspect}"></div>', unsafe_allow_html=True)
    return ph


def video_progress():
    """A live status box with a progress bar; returns (progress_callback, finish)."""
    t0 = time.time()
    box = st.status("🎬 Creating your video…", expanded=True)
    with box:
        ph = shimmer("16/9")
        bar = st.progress(0.0)
        note = st.empty()
    state = {"frac": 0.0}

    def cb(text, frac):
        if frac is not None:
            state["frac"] = max(state["frac"], min(1.0, frac))
        else:  # no real progress from the engine: creep forward so the bar never looks frozen
            state["frac"] = min(0.9, state["frac"] + 0.004)
        bar.progress(state["frac"])
        note.caption(f"{text} · {int(time.time() - t0)}s")

    def finish(ok, label):
        ph.empty()
        box.update(label=label, state="complete" if ok else "error", expanded=False)

    return cb, finish


def brand(size="sm"):
    c1, c2 = st.columns([1, 6] if size == "sm" else [1, 5], vertical_alignment="center", gap="small")
    c1.image(MARK, width=40 if size == "sm" else 72)
    c2.markdown('<p class="cy-brand">CYBOK</p>', unsafe_allow_html=True)


# ------------------------------------------------------------------ sessions ("remember me" cookie)
def signer():
    return URLSafeTimedSerializer(flask_app().config["SECRET_KEY"], salt="cybok-streamlit-session")


def set_cookie(value, days):
    st.html(f"<script>document.cookie = '{COOKIE}=' + {json.dumps(value)} + "
            f"'; path=/; max-age={days * 86400}; SameSite=Lax';</script>", unsafe_allow_javascript=True)


def current_user():
    if "uid" not in ss:
        token = st.context.cookies.get(COOKIE)
        if token and not ss.get("signed_out"):
            try:
                data = signer().loads(token, max_age=REMEMBER_DAYS * 86400)
                ss.uid, ss.ver = data["uid"], data["v"]
            except (BadSignature, KeyError, TypeError):
                pass
    user = sv.load_user(ss.get("uid"), ss.get("ver"))
    if user is None and "uid" in ss:
        del ss["uid"]
    return user


def sign_in(user, remember):
    ss.uid, ss.ver = user.id, user.session_version
    ss.signed_out = False
    if remember:
        ss.set_cookie = signer().dumps({"uid": user.id, "v": user.session_version})
    st.rerun()


def sign_out():
    for k in list(ss.keys()):
        del ss[k]
    ss.signed_out = True
    ss.clear_cookie = True
    st.rerun()


def base_url():
    try:
        return st.context.url.split("?")[0].rstrip("/")
    except Exception:
        return "http://localhost:5000"


def go(page, **extra):
    ss.page = page
    for k, v in extra.items():
        ss[k] = v
    st.rerun()


# ------------------------------------------------------------------ rendering helpers
def render_md(text, owner_id):
    """Markdown with Cybok's extras: reasoning blocks, generated images, small print."""
    text = text or ""
    for thought in THINK_RE.findall(text):
        if thought.strip():
            with st.expander("Thought process"):
                st.markdown(thought)
    text = SUB_RE.sub(lambda m: f"\n\n*{m.group(1).strip()}*", THINK_RE.sub("", text))
    pos = 0
    for m in MEDIA_RE.finditer(text):
        if text[pos:m.start()].strip():
            st.markdown(text[pos:m.start()])
        f = sv.files_by_id(owner_id, [m.group(2)]).get(m.group(2))
        if f:
            show_media(f, caption=m.group(1) or None)
        pos = m.end()
    if text[pos:].strip():
        st.markdown(text[pos:])


def thumb(f):
    p = abs_path(f.storage_path)
    t = Path(str(p) + ".thumb.webp")
    return str(t if t.exists() else p)


def show_media(f, caption=None, small=False):
    if f.kind == "video":
        st.video(str(abs_path(f.storage_path)))
        if caption:
            st.caption(caption)
    else:
        st.image(thumb(f) if small else str(abs_path(f.storage_path)), caption=caption)


def render_attachments(msg, owner_id):
    fmap = sv.files_by_id(owner_id, msg.attachment_ids)
    files = [fmap[i] for i in msg.attachment_ids if i in fmap]
    pics = [f for f in files if f.kind == "image"]
    if pics:
        cols = st.columns(min(4, len(pics)))
        for c, f in zip(cols, pics):
            c.image(thumb(f), caption=f.name)
    for f in files:
        if f.kind != "image":
            st.caption(f"📎 {f.name} · {f.size / 1024:,.0f} KB")


def avatar_for(user):
    return sv.avatar_path(user) or "👤"


def model_label(slug, models):
    m = models.get(slug)
    if not m:
        return slug
    tags = [t for t in (m.badge, "👁 Vision" if m.supports_vision else "") if t]
    return f"{m.name}  ·  {m.provider}" + (f"  ({', '.join(tags)})" if tags else "")


# ------------------------------------------------------------------ auth pages
def page_auth():
    css()
    _, mid, _ = st.columns([1, 2, 1])
    with mid:
        brand("lg")
        st.markdown('<div class="cy-hero">Your AI.<br>Your Workspace.</div>', unsafe_allow_html=True)
        st.markdown('<p class="cy-tag">Free AI chat, images, logos and file analysis — all in one place.</p>',
                    unsafe_allow_html=True)
        token = st.query_params.get("reset")
        if token:
            st.subheader("Set a new password")
            with st.form("reset"):
                pw = st.text_input("New password", type="password")
                pw2 = st.text_input("Repeat password", type="password")
                if st.form_submit_button("Update password", type="primary"):
                    try:
                        sv.reset_password(token, pw, pw2)
                        st.query_params.clear()
                        st.success("Your password has been updated. Please sign in.")
                    except sv.ServiceError as exc:
                        st.error(str(exc))
            return
        t_in, t_up, t_forgot = st.tabs(["Sign in", "Create account", "Forgot password"])
        with t_in, st.form("login"):
            email = st.text_input("E-mail")
            pw = st.text_input("Password", type="password")
            remember = st.checkbox("Keep me signed in", value=True)
            if st.form_submit_button("Sign in", type="primary", width="stretch"):
                try:
                    sign_in(sv.login(email, pw), remember)
                except sv.ServiceError as exc:
                    st.error(str(exc))
        with t_up:
            if not sv.registration_open():
                st.info("New registrations are currently closed.")
            else:
                with st.form("signup"):
                    name = st.text_input("Your name")
                    email = st.text_input("E-mail ")
                    pw = st.text_input("Password ", type="password", help="At least 8 characters.")
                    pw2 = st.text_input("Repeat password", type="password")
                    terms = st.checkbox("I accept the terms: use Cybok lawfully, don't abuse the free AI providers, "
                                        "and remember AI answers can be wrong.")
                    if st.form_submit_button("Create account", type="primary", width="stretch"):
                        try:
                            sign_in(sv.signup(name, email, pw, pw2, terms), True)
                        except sv.ServiceError as exc:
                            st.error(str(exc))
        with t_forgot, st.form("forgot"):
            email = st.text_input("Account e-mail")
            if st.form_submit_button("Send reset link"):
                try:
                    sv.forgot_password(email, base_url())
                    msg = "If an account exists for that e-mail, a reset link has been sent."
                    if not flask_app().config.get("MAIL_SERVER"):
                        msg += " (E-mail isn't configured, so the link was printed in the server console window.)"
                    st.success(msg)
                except sv.ServiceError as exc:
                    st.error(str(exc))
        st.caption(f"Cybok · Manufactured by {flask_app().config['CREATOR_NAME']} — "
                   f"{flask_app().config['CREATOR_DESCRIPTION']}")


def page_shared(token):
    css()
    conv = sv.shared_conv(token)
    brand()
    if not conv:
        st.error("This shared chat doesn't exist or is no longer shared.")
        return
    st.title(conv.title)
    st.caption("Shared conversation · read-only")
    for m in conv.messages.all():
        with st.chat_message(m.role, avatar=MARK if m.role == "assistant" else "👤"):
            render_md(m.content, conv.user_id)
            render_attachments(m, conv.user_id)
    st.divider()
    st.link_button("Try Cybok", base_url())


# ------------------------------------------------------------------ sidebar
def sidebar(user):
    with st.sidebar:
        brand()
        if st.button("✏️  New chat", width="stretch", type="primary"):
            go("chat", cid=None)
        for page, label in (("image", "🎨  Create image"), ("video", "🎬  Create video"), ("logo", "✨  Logo studio"),
                            ("library", "📚  Library"), ("search", "🔍  Search")):
            if st.button(label, width="stretch", type="tertiary", key=f"nav-{page}"):
                go(page)
        view = st.segmented_control("Chats", ["active", "archived", "trash"], default=ss.get("view", "active"),
                                    format_func=str.title, key="view_sel")
        ss.view = view or "active"
        chats = sv.list_chats(user, ss.view)
        if not chats:
            st.caption("No chats here yet.")
        for c in chats[:80]:
            current = c.id == ss.get("cid") and ss.get("page", "chat") == "chat"
            label = ("📌 " if c.pinned else "") + c.title
            if st.button(label, key=f"chat-{c.id}", width="stretch", type="secondary" if current else "tertiary"):
                go("chat", cid=c.id)
        if ss.view == "trash" and chats:
            if st.button("🗑  Empty trash", width="stretch"):
                sv.empty_trash(user)
                st.rerun()
        st.divider()
        if st.button("⚙️  Settings", width="stretch", type="tertiary"):
            go("settings")
        if user.is_admin and st.button("🛡️  Admin", width="stretch", type="tertiary"):
            go("admin")
        c1, c2 = st.columns([1, 4], vertical_alignment="center")
        c1.image(avatar_for(user) if avatar_for(user) != "👤" else MARK, width=32)
        c2.markdown(f"**{user.name}**  \n<span style='font-size:.8rem;opacity:.7'>{user.email}</span>",
                    unsafe_allow_html=True)
        if st.button("Sign out", width="stretch"):
            sign_out()


# ------------------------------------------------------------------ chat
def chat_menu(user, conv):
    with st.popover("⋯", help="Chat options"):
        title = st.text_input("Rename", conv.title, key=f"ren-{conv.id}")
        if title != conv.title and st.button("Save title"):
            sv.update_chat(conv, title=title)
            st.rerun()
        if conv.deleted_at is not None:
            if st.button("♻️ Restore", width="stretch"):
                sv.restore_chat(conv)
                st.rerun()
            if st.button("Delete forever", width="stretch"):
                sv.delete_chat(conv, permanent=True)
                go("chat", cid=None)
            return
        if st.button("📌 Unpin" if conv.pinned else "📌 Pin", width="stretch"):
            sv.update_chat(conv, pinned=not conv.pinned)
            st.rerun()
        if st.button("📦 Unarchive" if conv.archived else "📦 Archive", width="stretch"):
            sv.update_chat(conv, archived=not conv.archived)
            st.rerun()
        text, name = sv.export_chat(conv)
        st.download_button("⬇️ Export (.md)", text, file_name=name, mime="text/markdown", width="stretch")
        shared = st.toggle("🔗 Share link", value=bool(conv.share_enabled and conv.share_token))
        if shared != bool(conv.share_enabled and conv.share_token):
            sv.set_share(conv, shared)
            st.rerun()
        if shared:
            st.code(f"{base_url()}/?share={conv.share_token}", language=None)
            if st.button("New link (old one stops working)"):
                sv.set_share(conv, True, regenerate=True)
                st.rerun()
        if st.button("🗑 Delete", width="stretch"):
            sv.delete_chat(conv)
            go("chat", cid=None)


def message_actions(user, conv, m, is_last):
    cols = st.columns([0.6, 0.6, 0.6, 0.6, 0.6, 10], gap="small")
    if cols[0].button("👍", key=f"up{m.id}", type="primary" if m.feedback == 1 else "tertiary", help="Good answer"):
        sv.set_feedback(user, m.id, 1)
        st.rerun()
    if cols[1].button("👎", key=f"dn{m.id}", type="primary" if m.feedback == -1 else "tertiary", help="Bad answer"):
        sv.set_feedback(user, m.id, -1)
        st.rerun()
    with cols[2].popover("📋", help="Copy"):
        st.code(THINK_RE.sub("", m.content or ""), language=None, wrap_lines=True)
    if cols[3].button("💾", key=f"sv{m.id}", type="tertiary", help="Save to Library"):
        sv.save_message(user, m.id)
        st.toast("Saved to your Library.")
    media = m.model in ("image", "video")
    if is_last and not media and cols[4].button("🔄", key=f"rg{m.id}", type="tertiary", help="Regenerate"):
        ss.pending = {"mode": "regenerate"}
        st.rerun()
    if m.model and not media:
        cols[5].caption(model_label(m.model, {x.slug: x for x in AIModel.query.all()}).split("  ·  ")[0])


def transcribe(audio):
    """Voice dictation through Groq's free Whisper endpoint."""
    r = requests.post("https://api.groq.com/openai/v1/audio/transcriptions",
                      headers={"Authorization": f"Bearer {get_secret('GROQ_API_KEY')}"},
                      files={"file": ("voice.wav", audio.getvalue(), "audio/wav")},
                      data={"model": "whisper-large-v3-turbo"}, timeout=60)
    if r.status_code != 200:
        raise sv.ServiceError("Couldn't transcribe the recording. Please try again or type your message.")
    return r.json().get("text", "").strip()


def stream_answer(turn):
    with st.chat_message("assistant", avatar=MARK):
        gen = sv.stream_turn(turn)
        try:
            st.write_stream(gen)
        finally:
            gen.close()  # a rerun (e.g. pressing Stop) interrupts here; the partial answer is still saved
    for n in turn.get("notices", []):
        st.toast(n)
    sv.auto_title(turn)


def page_chat(user):
    conv = sv.own_conv(user, ss.cid, include_deleted=True) if ss.get("cid") else None
    if conv is None:
        ss.cid = None
    models = {m.slug: m for m in enabled_models()}
    available = [s for s, m in models.items() if is_available(m)]
    s = sv.settings_for(user)

    maint = all_settings().get("maintenance_message")
    if maint:
        st.warning(maint)
    for a in sv.active_announcements():
        getattr(st, {"success": "success", "warning": "warning"}.get(a.level, "info"))(f"**{a.title}**  \n{a.body}")

    head, menu = st.columns([12, 1], vertical_alignment="center")
    if conv:
        head.subheader(conv.title + ("  ·  temporary" if conv.temporary else ""))
        with menu:
            chat_menu(user, conv)
    else:
        head.markdown(f'<div class="cy-hero">Hi {user.name.split()[0]}, how can I help?</div>',
                      unsafe_allow_html=True)

    if not available:
        st.error("No AI model is ready yet. An admin can turn one on for free in **Admin › Free AI keys** "
                 "(paste a free Groq key) or by installing Ollama and running `ollama pull llama3.2`.")
    current = (conv.model if conv else None) or s.default_model
    current = current if current in available else default_model_slug()
    c0, c1, c2 = st.columns([2, 3, 1], vertical_alignment="center")
    mode = c0.segmented_control("Mode", ["chat", "image", "video"], default="chat", key="chat_mode",
                                format_func={"chat": "💬 Chat", "image": "🎨 Image", "video": "🎬 Video"}.get,
                                label_visibility="collapsed") or "chat"
    model_slug = c1.selectbox("Model", available, index=available.index(current) if current in available else 0,
                              format_func=lambda x: model_label(x, models), key=f"model-{ss.get('cid')}",
                              label_visibility="collapsed", disabled=mode != "chat") if available else None
    temporary = c2.toggle("Temporary chat", help="Not saved in your history.") if not conv else conv.temporary

    if conv:
        msgs = conv.messages.all()
        last_user = max((m.id for m in msgs if m.role == "user"), default=None)
        last_asst = max((m.id for m in msgs if m.role == "assistant"), default=None)
        for m in msgs:
            if m.role == "user":
                with st.chat_message("user", avatar=avatar_for(user)):
                    if m.content:
                        st.markdown(m.content)
                    render_attachments(m, user.id)
                    if m.id == last_user and conv.deleted_at is None:
                        with st.popover("✏️", help="Edit and resend"):
                            new = st.text_area("Edit message", m.content, key=f"ed{m.id}")
                            if st.button("Save & resend", key=f"eds{m.id}", type="primary"):
                                ss.pending = {"mode": "edit", "message_id": m.id, "content": new}
                                st.rerun()
            else:
                with st.chat_message("assistant", avatar=MARK):
                    render_md(m.content, user.id)
                    if m.status == "error" and m.model not in ("image", "video"):
                        st.caption("⚠️ This answer failed. Press 🔄 to try again.")
                    if conv.deleted_at is None:
                        message_actions(user, conv, m, m.id == last_asst)

    if conv and conv.deleted_at is not None:
        st.info("This chat is in the Trash. Restore it from the ⋯ menu to continue.")
        return

    placeholder = {"image": "Describe the image to create (FLUX.1 Krea)…",
                   "video": "Describe the video to create (Wan2.1, takes ~1 min)…"}.get(
        mode, "Message Cybok…  (/image or /video to create media)")
    prompt = st.chat_input(placeholder, accept_file="multiple",
                           file_type=sorted(ALLOWED_EXT), accept_audio=bool(get_secret("GROQ_API_KEY")),
                           disabled=not available and mode == "chat")
    pending = ss.pop("pending", None)
    if not (prompt or pending) or (not model_slug and mode == "chat"):
        return
    if conv is None:
        conv = sv.create_chat(user, model_slug, temporary=temporary)
        ss.cid = conv.id
    try:
        if pending:
            turn = sv.prepare_turn(user, conv, model_slug, mode=pending["mode"], content=pending.get("content", ""),
                                   message_id=pending.get("message_id"))
            stream_answer(turn)
            st.rerun()
        text = (prompt.text or "").strip()
        if getattr(prompt, "audio", None):
            with st.spinner("Listening…"):
                text = (text + " " + transcribe(prompt.audio)).strip()
        if text.lower().startswith(("/image", "/video")):
            mode, text = text[1:6].lower(), text[6:].strip()
        if mode in ("image", "video"):
            with st.chat_message("user", avatar=avatar_for(user)):
                st.markdown(("🎨 Create image: " if mode == "image" else "🎬 Create video: ") + text)
        if mode == "image":
            with st.chat_message("assistant", avatar=MARK):
                shimmer()
                with st.spinner("Painting your image with FLUX.1 Krea…"):
                    sv.chat_image(user, conv, text)
            st.rerun()
        if mode == "video":
            with st.chat_message("assistant", avatar=MARK):
                cb, finish = video_progress()
                sv.chat_video(user, conv, text, cb)
                finish(True, "Video ready")
            st.rerun()
        ids = []
        for f in prompt.files:
            try:
                ids.append(sv.upload(user, f.name, f.getvalue()).id)
            except sv.ServiceError as exc:
                st.toast(f"{f.name}: {exc}")
        with st.chat_message("user", avatar=avatar_for(user)):
            st.markdown(text)
            for f in prompt.files:
                st.caption(f"📎 {f.name}")
        turn = sv.prepare_turn(user, conv, model_slug, content=text, attachments=ids)
        st.button("⏹ Stop", key="stop", type="tertiary")
        stream_answer(turn)
    except sv.ServiceError as exc:
        st.error(str(exc))
        return
    st.rerun()


# ------------------------------------------------------------------ images & logos
def gen_card(user, g, col):
    with col:
        if g.file:
            show_media(g.file, small=True)
        elif g.output:
            st.image(g.output)
        st.caption(g.title)
        a, b, c = st.columns(3)
        if g.file:
            p = abs_path(g.file.storage_path)
            if p.exists():
                a.download_button("⬇️", p.read_bytes(), file_name=g.file.name, mime=g.file.mime, key=f"dl{g.id}")
        elif g.output:
            name = re.sub(r"[^A-Za-z0-9 _-]", "", g.title or "logo")[:60].strip() or "logo"
            a.download_button("⬇️", g.output, file_name=f"{name}.svg", mime="image/svg+xml", key=f"dl{g.id}")
        if b.button("★" if g.saved else "☆", key=f"st{g.id}", help="Saved in Library" if g.saved else "Save to Library"):
            sv.toggle_saved(g)
            st.rerun()
        if c.button("🗑", key=f"del{g.id}"):
            sv.delete_generated(g)
            st.rerun()


def grid(user, items, n=4):
    for i in range(0, len(items), n):
        cols = st.columns(n)
        for g, col in zip(items[i:i + n], cols):
            gen_card(user, g, col)


def page_image(user):
    st.title("🎨 Create image")
    with st.form("img"):
        prompt = st.text_area("Describe your image", placeholder="A cozy cabin in snowy mountains at sunset")
        providers = list(image_ai.PROVIDERS)
        default = all_settings().get("image_provider")
        provider = st.selectbox("Image model", providers, index=providers.index(default) if default in providers else 0,
                                format_func=lambda p: image_ai.PROVIDERS[p][0],
                                help="FLUX.1 Krea [dev] gives the most natural, photographic results. It needs "
                                     "HF_TOKEN; if it fails, Cybok falls back to the free Pollinations model.")
        c1, c2, c3 = st.columns(3)
        style = c1.selectbox("Style", list(image_ai.STYLES), format_func=lambda k: image_ai.STYLES[k][0])
        size = c2.selectbox("Size", list(image_ai.SIZES),
                            format_func=lambda k: f"{k.title()} ({image_ai.SIZES[k][0]}×{image_ai.SIZES[k][1]})")
        count = c3.slider("Images", 1, 4, 1)
        go_btn = st.form_submit_button("Generate", type="primary")
    if go_btn:
        if not prompt.strip():
            st.error("Describe the image you want.")
        else:
            w, h = image_ai.SIZES[size]
            ph = shimmer(f"{w}/{h}", min(count, 4))
            with st.spinner("Creating your image… free GPUs can take up to a minute."):
                try:
                    items = sv.generate_images(user, sv.clean_text(prompt, 1500), style, size, count, "image",
                                               provider=provider)
                    for label in {json.loads(g.meta or "{}").get("provider", "") for g in items}:
                        if "fallback" in label:
                            st.warning(f"Generated with {label}. FLUX.1 Krea's free GPU time was busy or used up — "
                                       "add a free Hugging Face token (HF_TOKEN in Admin › Free AI keys) for more.")
                        else:
                            st.success(f"Generated with {label}")
                except (sv.ServiceError, image_ai.ImageError) as exc:
                    st.error(str(exc))
            ph.empty()
    st.subheader("Recent")
    grid(user, sv.list_generated(user, "image", 24))


def page_video(user):
    st.title("🎬 Create video")
    st.caption(f"Text-to-video with **{video_ai.VIDEO_MODEL}** on free Hugging Face GPUs. A clip takes 1–4 minutes.")
    with st.form("vid"):
        prompt = st.text_area("Describe your video", placeholder="A corgi running on a beach at golden hour, "
                                                                 "slow motion, cinematic")
        go_btn = st.form_submit_button("Generate video", type="primary")
    if go_btn:
        cb, finish = video_progress()
        try:
            g = sv.generate_video(user, prompt, cb)
            finish(True, f"Video ready · {json.loads(g.meta)['provider']}")
        except (sv.ServiceError, image_ai.ImageError) as exc:
            finish(False, "Video failed")
            st.error(str(exc))
    st.subheader("Recent")
    grid(user, sv.list_generated(user, "video", 12), n=2)


def page_logo(user):
    st.title("✨ Logo studio")
    st.caption("Instant vector logos (SVG) plus optional AI concepts.")
    with st.form("logo"):
        c1, c2 = st.columns(2)
        brand_name = c1.text_input("Brand name *")
        industry = c2.text_input("Industry", placeholder="tech, food, fitness…")
        style = c1.text_input("Style", placeholder="modern, luxury, playful…")
        colors = c2.text_input("Colors", placeholder="red and blue, #ff3448…")
        symbol = c1.text_input("Symbol", placeholder="bolt, leaf, shield…")
        typo = c2.text_input("Typography", placeholder="geometric, serif, bold…")
        ai_count = st.slider("AI concepts (slower)", 0, 2, 0)
        go_btn = st.form_submit_button("Generate logos", type="primary")
    if go_btn:
        with st.spinner("Designing…"):
            try:
                _, ai_error = sv.create_logos(user, ai_count, brand=brand_name, industry=industry, style=style,
                                              colors=colors, symbol=symbol, typography=typo)
                if ai_error:
                    st.warning(f"Vector logos are ready, but the AI concepts failed: {ai_error}")
            except sv.ServiceError as exc:
                st.error(str(exc))
    st.subheader("Recent")
    grid(user, sv.list_generated(user, "logo", 24), n=3)


# ------------------------------------------------------------------ library & search
def page_library(user):
    st.title("📚 Library")
    c1, c2, c3, c4 = st.columns([2, 3, 2, 2])
    t = c1.selectbox("Type", ["all", "document", "data", "code", "image", "video", "logo", "text"],
                     format_func=str.title)
    q = c2.text_input("Search", placeholder="Search names and contents")
    items, folders, used = sv.library(user, t, q, "__all__", "new")
    folder = c3.selectbox("Folder", ["__all__"] + folders, format_func=lambda f: "All folders" if f == "__all__" else f)
    sort = c4.selectbox("Sort", ["new", "old", "name", "size"], format_func=lambda s: {
        "new": "Newest", "old": "Oldest", "name": "Name", "size": "Largest"}[s])
    items, _, _ = sv.library(user, t, q, folder, sort)
    with st.expander("⬆️ Upload files"):
        ups = st.file_uploader("Add to Library", accept_multiple_files=True, type=sorted(ALLOWED_EXT),
                               label_visibility="collapsed", key=f"lib-up-{ss.get('lib_up', 0)}")
        if ups and st.button("Upload", type="primary"):
            for f in ups:
                try:
                    sv.upload(user, f.name, f.getvalue())
                except sv.ServiceError as exc:
                    st.error(f"{f.name}: {exc}")
            ss.lib_up = ss.get("lib_up", 0) + 1
            st.rerun()
    st.caption(f"{len(items)} items · {used / 1048576:,.1f} MB used")
    for kind, obj in items[:150]:
        is_file = kind == "file"
        title = obj.name if is_file else obj.title
        icon = {"image": "🖼", "data": "📊", "code": "💻", "logo": "✨", "text": "📝", "video": "🎬"}.get(
            obj.kind if is_file else obj.content_type, "📄")
        with st.expander(f"{icon} {title}" + (f"  ·  📁 {obj.folder}" if obj.folder else "")):
            if is_file:
                p = abs_path(obj.storage_path)
                if obj.kind == "image":
                    st.image(thumb(obj))
                elif obj.extracted_text:
                    st.text(obj.extracted_text[:3000] + ("…" if len(obj.extracted_text) > 3000 else ""))
                st.caption(f"{obj.size / 1024:,.0f} KB · {obj.created_at:%Y-%m-%d %H:%M}")
                if p.exists():
                    st.download_button("⬇️ Download", p.read_bytes(), file_name=obj.name, mime=obj.mime,
                                       key=f"ldl{obj.id}")
            else:
                if obj.file:
                    show_media(obj.file, small=True)
                elif obj.content_type == "logo" and obj.output:
                    st.image(obj.output)
                else:
                    st.markdown(obj.output or "")
                    st.download_button("⬇️ Download (.md)", obj.output or "", file_name=f"{title[:50]}.md",
                                       key=f"ldl{obj.id}")
            with st.form(f"lib-edit-{obj.id}"):
                a, b = st.columns(2)
                new_title = a.text_input("Name", title)
                new_folder = b.text_input("Folder", obj.folder or "")
                s1, s2 = st.columns(2)
                if s1.form_submit_button("Save"):
                    sv.rename_item(kind, obj, new_title, new_folder)
                    st.rerun()
                if s2.form_submit_button("🗑 Delete"):
                    sv.delete_item(kind, obj)
                    st.rerun()


def page_search(user):
    st.title("🔍 Search")
    q = st.text_input("Search chats, messages, files and creations", key="q")
    chats, files, gens = sv.search(user, q)
    if q and len(q.strip()) >= 2 and not (chats or files or gens):
        st.info("No results.")
    if chats:
        st.subheader("Chats")
        for c, snippet in chats:
            if st.button(c.title, key=f"sr{c.id}", type="tertiary"):
                go("chat", cid=c.id)
            if snippet:
                st.caption(snippet)
    if files:
        st.subheader("Files")
        for f in files:
            st.write(f"📄 {f.name}")
    if gens:
        st.subheader("Creations")
        for g in gens:
            st.write(f"✨ {g.title}")


# ------------------------------------------------------------------ settings
def page_settings(user):
    st.title("⚙️ Settings")
    s = sv.settings_for(user)
    t_acc, t_chat, t_data, t_about = st.tabs(["Account", "Chat", "Data & privacy", "About"])
    with t_acc:
        c1, c2 = st.columns([1, 3])
        c1.image(sv.avatar_path(user) or MARK, width=110)
        with c2:
            pic = st.file_uploader("Profile photo", type=["png", "jpg", "jpeg", "webp", "gif"],
                                   key=f"av-{ss.get('av', 0)}")
            if pic:
                try:
                    sv.set_avatar(user, pic.getvalue())
                    ss.av = ss.get("av", 0) + 1
                    st.rerun()
                except sv.ServiceError as exc:
                    st.error(str(exc))
        with st.form("profile"):
            name = st.text_input("Name", user.name)
            email = st.text_input("E-mail", user.email)
            cur = st.text_input("Current password (only needed to change e-mail)", type="password")
            if st.form_submit_button("Save profile", type="primary"):
                try:
                    sv.update_profile(user, name, email, cur)
                    st.success("Profile saved.")
                except sv.ServiceError as exc:
                    st.error(str(exc))
        with st.form("pw"):
            st.markdown("**Change password**")
            cur = st.text_input("Current password", type="password") if user.password_hash else ""
            new = st.text_input("New password", type="password")
            new2 = st.text_input("Repeat new password", type="password")
            if st.form_submit_button("Change password"):
                try:
                    sv.change_password(user, cur, new, new2)
                    ss.ver = user.session_version
                    st.success("Password changed. Other devices were signed out.")
                except sv.ServiceError as exc:
                    st.error(str(exc))
    with t_chat, st.form("chat-settings"):
        models = [m for m in enabled_models() if is_available(m)]
        slugs = [""] + [m.slug for m in models]
        names = {m.slug: m.name for m in models}
        default_model = st.selectbox("Default model", slugs, index=slugs.index(s.default_model) if s.default_model in slugs else 0,
                                     format_func=lambda x: names.get(x, "Automatic (best available)"))
        styles = ["concise", "balanced", "detailed"]
        style = st.radio("Response style", styles, index=styles.index(s.response_style or "balanced"),
                         format_func=str.title, horizontal=True)
        ci = st.text_area("Custom instructions", s.custom_instructions or "", max_chars=3000,
                          placeholder="e.g. I'm a computer science student. Explain things simply and give "
                                      "code examples in Python.")
        sizes = ["sm", "md", "lg"]
        fs = st.radio("Chat text size", sizes, index=sizes.index(s.font_size or "md"),
                      format_func={"sm": "Small", "md": "Default", "lg": "Large"}.get, horizontal=True)
        hist = st.toggle("Save chat history", s.save_history)
        notif = st.toggle("Security e-mails (password / e-mail changes)", s.email_notifications)
        st.caption("Light / dark theme: use the ⋮ menu (top right) › Settings.")
        if st.form_submit_button("Save", type="primary"):
            sv.update_settings(user, default_model=default_model, response_style=style, custom_instructions=ci,
                               font_size=fs, save_history=hist, email_notifications=notif)
            st.success("Settings saved.")
            st.rerun()
    with t_data:
        st.download_button("⬇️ Export my data (JSON)", sv.export_account(user), file_name="cybok-export.json",
                           mime="application/json")
        if st.button("Sign out of all devices"):
            user.session_version += 1
            db.session.commit()
            sign_out()
        with st.form("delete-acc"):
            st.markdown("**Delete account** — permanently removes your chats, files and creations.")
            pw = st.text_input("Password", type="password") if user.password_hash else ""
            confirm = "" if user.password_hash else st.text_input("Type DELETE to confirm")
            if st.form_submit_button("Delete my account"):
                try:
                    sv.delete_account(user, pw, confirm)
                    sign_out()
                except sv.ServiceError as exc:
                    st.error(str(exc))
    with t_about:
        c = flask_app().config
        st.markdown(f"**{c['APP_NAME']}** {c['VERSION']} — {c['TAGLINE']}  \nManufactured by **{c['CREATOR_NAME']}** "
                    f"— {c['CREATOR_DESCRIPTION']}")
        st.caption("Chat with free open models (Groq, OpenRouter, Ollama, Pollinations) with automatic fallback, "
                   "create images and logos, and analyse PDF, Word, Excel, PowerPoint, code and images.")


# ------------------------------------------------------------------ admin
def model_form(m, key):
    with st.form(key):
        c1, c2, c3 = st.columns(3)
        d = {
            "name": c1.text_input("Name", m.name if m else ""),
            "slug": c2.text_input("Slug", m.slug if m else ""),
            "provider": c3.text_input("Provider", m.provider if m else ""),
            "model_family": c1.text_input("Family", m.model_family if m else ""),
            "api_base": c2.text_input("API base URL", m.api_base if m else "https://"),
            "api_model": c3.text_input("API model", m.api_model if m else ""),
            "api_key_env": c1.text_input("Key env var", m.api_key_env if m else ""),
            "api_key": c2.text_input("API key (optional, stored)", type="password"),
            "badge": c3.text_input("Badge", m.badge if m else ""),
            "description": st.text_input("Description", m.description if m else ""),
        }
        n1, n2, n3, n4 = st.columns(4)
        d["temperature"] = n1.number_input("Temperature", 0.0, 2.0, float(m.temperature if m else 0.7), 0.1)
        d["max_tokens"] = n2.number_input("Max tokens", 16, 64000, int(m.max_tokens if m else 2048))
        d["context_chars"] = n3.number_input("Context chars", 2000, 500000, int(m.context_chars if m else 24000))
        d["sort_order"] = n4.number_input("Sort order", 0, 10000, int(m.sort_order if m else 100))
        b1, b2, b3, b4 = st.columns(4)
        d["enabled"] = b1.checkbox("Enabled", m.enabled if m else True)
        d["key_required"] = b2.checkbox("Key required", m.key_required if m else True)
        d["supports_vision"] = b3.checkbox("Vision", m.supports_vision if m else False)
        d["supports_streaming"] = b4.checkbox("Streaming", m.supports_streaming if m else True)
        a1, a2, a3 = st.columns(3)
        if a1.form_submit_button("Save", type="primary"):
            try:
                sv.save_model(m, d)
                st.success("Saved.")
                st.rerun()
            except (sv.ServiceError, ValueError) as exc:
                st.error(str(exc))
        if m and a2.form_submit_button("Test"):
            with st.spinner("Asking the model…"):
                ok, msg = sv.test_model(m)
            (st.success if ok else st.error)(msg)
        if m and a3.form_submit_button("🗑 Delete"):
            sv.delete_row(m)
            st.rerun()


def page_admin(user):
    if not user.is_admin:
        st.error("Admins only.")
        return
    st.title("🛡️ Admin")
    tabs = st.tabs(["Overview", "Users", "AI models", "Free AI keys", "System", "Announcements", "Error log"])
    with tabs[0]:
        stats, series, model_rows = sv.admin_stats()
        cols = st.columns(6)
        for i, (k, v) in enumerate(stats.items()):
            cols[i % 6].metric(k, v)
        st.subheader("Activity · last 14 days")
        st.line_chart(pd.DataFrame(series).T)
        if model_rows:
            st.subheader("Chat requests by model")
            st.bar_chart(pd.DataFrame(model_rows, columns=["Model", "Requests"]).set_index("Model"))
    with tabs[1]:
        q = st.text_input("Search users")
        users = sv.admin_users(q)
        st.dataframe(pd.DataFrame([{"ID": u.id, "Name": u.name, "E-mail": u.email, "Role": u.role,
                                    "Disabled": u.disabled, "Joined": u.created_at, "Last seen": u.last_seen_at}
                                   for u in users]), hide_index=True, width="stretch")
        if users:
            pick = st.selectbox("Manage user", users, format_func=lambda u: f"{u.name} <{u.email}>")
            c1, c2, c3 = st.columns(3)
            try:
                if c1.button("Enable" if pick.disabled else "Disable"):
                    sv.admin_update_user(user, pick.id, disabled=not pick.disabled)
                    st.rerun()
                if c2.button("Make user" if pick.is_admin else "Make admin"):
                    sv.admin_update_user(user, pick.id, role="user" if pick.is_admin else "admin")
                    st.rerun()
            except sv.ServiceError as exc:
                st.error(str(exc))
            sure = c3.checkbox("Confirm delete")
            if c3.button("🗑 Delete user", disabled=not sure or pick.id == user.id):
                sv.admin_delete_user(user, pick.id)
                st.rerun()
    with tabs[2]:
        for m in AIModel.query.order_by(AIModel.sort_order, AIModel.id).all():
            reason = unavailable_reason(m)
            state = "🟢" if m.enabled and not reason else ("⚪" if not m.enabled else "🟠")
            with st.expander(f"{state} {m.name} · {m.provider} · key {sv.model_key_status(m)}"):
                if reason:
                    st.caption(reason)
                model_form(m, f"model-{m.id}")
        with st.expander("➕ Add model (any OpenAI-compatible API)"):
            model_form(None, "model-new")
    with tabs[3]:
        st.caption("Keys from .env take priority. Pasted keys are stored in the database.")
        with st.form("keys"):
            vals = {}
            for k in sv.key_status():
                src = f" — set ({k['source']}) {k['hint']}" if k["set"] else " — not set"
                vals[k["name"]] = st.text_input(f"{k['label']}{src}", type="password", help=k["url"])
                st.caption(f"Get a free key: {k['url']}")
            if st.form_submit_button("Save keys", type="primary"):
                sv.save_keys(vals)
                st.success("Keys saved.")
                st.rerun()
    with tabs[4]:
        cur = all_settings()
        with st.form("system"):
            cd = st.text_input("Official creation date (YYYY-MM-DD, empty = not configured)", cur["creation_date"])
            reg = st.toggle("Registration open", cur["registration_open"] == "1")
            mx = st.number_input("Max upload (MB)", 1, 200, int(cur["max_upload_mb"] or 20))
            extra = st.text_area("Extra system prompt", cur["system_prompt_extra"], max_chars=2000)
            providers = list(image_ai.PROVIDERS)
            prov = st.selectbox("Image provider", providers, index=providers.index(cur["image_provider"])
                                if cur["image_provider"] in providers else 0,
                                format_func=lambda p: image_ai.PROVIDERS[p][0])
            img_model = st.text_input("Pollinations image model", cur["image_model"])
            hf_model = st.text_input("Hugging Face image model", cur["hf_image_model"])
            slugs = [""] + [m.slug for m in enabled_models()]
            dm = st.selectbox("Default model for everyone", slugs, index=slugs.index(cur["default_model"])
                              if cur["default_model"] in slugs else 0, format_func=lambda s: s or "Automatic")
            maint = st.text_input("Maintenance banner (empty = none)", cur["maintenance_message"])
            if st.form_submit_button("Save", type="primary"):
                try:
                    sv.save_system_settings(dict(creation_date=cd, registration_open=reg, max_upload_mb=mx,
                                                 system_prompt_extra=extra, image_provider=prov, image_model=img_model,
                                                 hf_image_model=hf_model, default_model=dm, maintenance_message=maint))
                    st.success("Saved.")
                except sv.ServiceError as exc:
                    st.error(str(exc))
    with tabs[5]:
        levels = ["info", "success", "warning"]
        with st.form("ann-new", clear_on_submit=True):
            st.markdown("**New announcement**")
            title = st.text_input("Title")
            body = st.text_area("Message")
            level = st.selectbox("Level", levels)
            if st.form_submit_button("Publish", type="primary"):
                try:
                    sv.save_announcement(None, title, body, level, True)
                    st.rerun()
                except sv.ServiceError as exc:
                    st.error(str(exc))
        for a in Announcement.query.order_by(Announcement.created_at.desc()).all():
            with st.expander(("🟢 " if a.active else "⚪ ") + a.title):
                with st.form(f"ann-{a.id}"):
                    title = st.text_input("Title", a.title)
                    body = st.text_area("Message", a.body)
                    level = st.selectbox("Level", levels, index=levels.index(a.level) if a.level in levels else 0)
                    active = st.checkbox("Active", a.active)
                    c1, c2 = st.columns(2)
                    if c1.form_submit_button("Save"):
                        sv.save_announcement(a, title, body, level, active)
                        st.rerun()
                    if c2.form_submit_button("🗑 Delete"):
                        sv.delete_row(a)
                        st.rerun()
    with tabs[6]:
        rows = ErrorLog.query.order_by(ErrorLog.created_at.desc()).limit(300).all()
        if st.button("Clear log", disabled=not rows):
            sv.clear_errors()
            st.rerun()
        st.dataframe(pd.DataFrame([{"Time": e.created_at, "Source": e.source, "User": e.user_id,
                                    "Message": e.message} for e in rows]), hide_index=True, width="stretch")


# ------------------------------------------------------------------ main
PAGES = {"chat": page_chat, "image": page_image, "video": page_video, "logo": page_logo, "library": page_library,
         "search": page_search, "settings": page_settings, "admin": page_admin}


def main():
    if ss.pop("clear_cookie", False):
        set_cookie("", 0)
    share = st.query_params.get("share")
    if share:
        page_shared(share)
        return
    user = current_user()
    if user is None:
        page_auth()
        return
    if "set_cookie" in ss:
        set_cookie(ss.pop("set_cookie"), REMEMBER_DAYS)
    if not ss.get("purged"):
        sv.purge_old(user)
        ss.purged = True
    css(sv.settings_for(user).font_size)
    sidebar(user)
    PAGES.get(ss.get("page", "chat"), page_chat)(user)


with flask_app().app_context():
    main()
