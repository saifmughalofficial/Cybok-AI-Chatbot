"""Pages: landing, app shell, public share view, and access-controlled media."""
from pathlib import Path

from flask import (Blueprint, abort, jsonify, redirect, render_template, request, send_file, url_for)
from flask_login import current_user, login_required

from ..ai.chat import enabled_models, model_public
from ..extensions import db
from ..files import abs_path
from ..models import Conversation, File, GeneratedContent, User

bp = Blueprint("main", __name__)


@bp.route("/")
def landing():
    models = [model_public(m) for m in enabled_models()]
    return render_template("landing.html", models=models)


@bp.route("/app")
@bp.route("/app/<path:subpath>")
@login_required
def app_shell(subpath=None):
    return render_template("app.html")


@bp.route("/share/<token>")
def shared(token):
    conv = Conversation.query.filter_by(share_token=token, share_enabled=True, deleted_at=None).first()
    if conv is None:
        abort(404, "This shared conversation doesn't exist or the link was disabled by its owner.")
    msgs = [m for m in conv.messages if m.status != "streaming" and m.content]
    return render_template("share.html", conv=conv, messages=msgs)


@bp.route("/share/<token>/file/<file_id>")
def shared_file(token, file_id):
    """Images inside a shared chat. Only files actually referenced by that chat are served."""
    conv = Conversation.query.filter_by(share_token=token, share_enabled=True, deleted_at=None).first_or_404()
    f = File.query.filter_by(id=file_id, user_id=conv.user_id).first_or_404()
    ref = f"/media/file/{file_id}"
    if not any(ref in (m.content or "") for m in conv.messages) or not (f.mime or "").startswith("image/"):
        abort(404)
    return _send_private(f, thumb=bool(request.args.get("thumb")))


@bp.route("/terms")
def terms():
    return render_template("terms.html")


@bp.route("/health")
def health():
    try:
        db.session.execute(db.text("SELECT 1"))
        return jsonify(status="ok")
    except Exception:
        return jsonify(status="db-error"), 500


@bp.route("/manifest.webmanifest")
def manifest():
    return jsonify({
        "name": "Cybok", "short_name": "Cybok", "start_url": "/app", "display": "standalone",
        "background_color": "#07080d", "theme_color": "#07080d", "description": "Your AI. Your Workspace.",
        "icons": [{"src": url_for("static", filename="img/icon-192.png"), "sizes": "192x192", "type": "image/png"},
                  {"src": url_for("static", filename="img/mark.png"), "sizes": "256x256", "type": "image/png"}],
    })


def _send_private(f, download=False, thumb=False):
    path = abs_path(f.storage_path)
    if thumb:
        tp = Path(str(path) + ".thumb.webp")
        if tp.exists():
            path = tp
    if not path.exists():
        abort(404)
    inline_ok = (f.mime or "").startswith("image/") or f.mime == "application/pdf"
    resp = send_file(path, mimetype="image/webp" if thumb and path.suffix == ".webp" else f.mime,
                     as_attachment=download or not inline_ok, download_name=f.name, max_age=3600,
                     conditional=True)
    resp.headers["Cache-Control"] = "private, max-age=3600"
    # Uploaded content must never execute as active content on our origin.
    resp.headers["Content-Security-Policy"] = "default-src 'none'; img-src 'self'; style-src 'unsafe-inline'; sandbox"
    return resp


@bp.route("/media/file/<file_id>")
@login_required
def media_file(file_id):
    f = File.query.filter_by(id=file_id, user_id=current_user.id).first_or_404()
    return _send_private(f, download=bool(request.args.get("download")), thumb=bool(request.args.get("thumb")))


@bp.route("/media/svg/<item_id>")
@login_required
def media_svg(item_id):
    g = GeneratedContent.query.filter_by(id=item_id, user_id=current_user.id, content_type="logo").first_or_404()
    if not g.output:
        abort(404)
    resp = current_app_response(g.output, "image/svg+xml")
    if request.args.get("download"):
        name = "".join(c for c in (g.title or "logo") if c.isalnum() or c in " -_").strip() or "logo"
        resp.headers["Content-Disposition"] = f'attachment; filename="{name}.svg"'
    return resp


def current_app_response(body, mimetype):
    from flask import Response
    resp = Response(body, mimetype=mimetype)
    resp.headers["Content-Security-Policy"] = "default-src 'none'; style-src 'unsafe-inline'; sandbox"
    resp.headers["Cache-Control"] = "private, max-age=3600"
    return resp


@bp.route("/media/avatar/<int:user_id>")
@login_required
def media_avatar(user_id):
    if user_id != current_user.id and not current_user.is_admin:
        abort(404)
    user = db.session.get(User, user_id)
    if not user or not user.avatar or user.avatar.startswith("http"):
        abort(404)
    path = abs_path(user.avatar)
    if not path.exists():
        abort(404)
    resp = send_file(path, mimetype="image/webp", max_age=86400)
    resp.headers["Cache-Control"] = "private, max-age=86400"
    return resp


@bp.route("/favicon.ico")
def favicon():
    return redirect(url_for("static", filename="img/favicon.ico"), code=301)
