"""Sign up, sign in, Google OAuth, password reset, logout."""
import secrets
from urllib.parse import urlparse

from flask import (Blueprint, current_app, flash, redirect, render_template, request, session,
                   url_for)
from flask_login import current_user, login_required, login_user, logout_user
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from ..appsettings import setting_bool
from ..extensions import db, oauth
from ..mailer import mail_configured, send_mail
from ..models import Conversation, User, UserSettings, utcnow
from ..security import (clean_text, password_problem, rate_limit, valid_email)

bp = Blueprint("auth", __name__)


def _serializer():
    return URLSafeTimedSerializer(current_app.config["SECRET_KEY"], salt="cybok-password-reset")


def _safe_next(target):
    if not target:
        return None
    p = urlparse(target)
    if p.scheme or p.netloc or not target.startswith("/") or target.startswith("//"):
        return None
    return target


def _external_url(endpoint, **values):
    base = current_app.config.get("PUBLIC_URL")
    if base:
        return base + url_for(endpoint, **values)
    return url_for(endpoint, _external=True, **values)


def finish_login(user, remember=True):
    if not user.settings:
        user.settings = UserSettings()
    # Bootstrap: the first account, or any e-mail in ADMIN_EMAILS, becomes an admin.
    if user.role != "admin" and (user.email.lower() in current_app.config["ADMIN_EMAILS"] or
                                 not User.query.filter_by(role="admin").count()):
        user.role = "admin"
    user.last_seen_at = utcnow()
    db.session.commit()
    session.permanent = True
    login_user(user, remember=remember)
    # Temporary chats (history turned off) do not survive a new session.
    Conversation.query.filter_by(user_id=user.id, temporary=True).delete()
    db.session.commit()


@bp.route("/login", methods=["GET", "POST"])
@rate_limit("auth", "RATE_AUTH_PER_5MIN", window=300, methods=("POST",))
def login():
    if current_user.is_authenticated:
        return redirect(url_for("main.app_shell"))
    if request.method == "POST":
        email = clean_text(request.form.get("email"), 255).lower()
        password = request.form.get("password") or ""
        user = User.query.filter_by(email=email).first()
        if not user or not user.check_password(password):
            flash("Incorrect e-mail or password.", "error")
            return render_template("auth/login.html", email=email), 401
        if user.disabled:
            flash("This account has been disabled. Contact the administrator.", "error")
            return render_template("auth/login.html", email=email), 403
        finish_login(user, remember=bool(request.form.get("remember")))
        return redirect(_safe_next(request.args.get("next")) or url_for("main.app_shell"))
    return render_template("auth/login.html")


@bp.route("/signup", methods=["GET", "POST"])
@rate_limit("auth", "RATE_AUTH_PER_5MIN", window=300, methods=("POST",))
def signup():
    if current_user.is_authenticated:
        return redirect(url_for("main.app_shell"))
    open_reg = setting_bool("registration_open") or not User.query.count()
    if request.method == "POST":
        if not open_reg:
            flash("New registrations are currently closed.", "error")
            return render_template("auth/signup.html", closed=True), 403
        name = clean_text(request.form.get("name"), 120)
        email = clean_text(request.form.get("email"), 255).lower()
        password = request.form.get("password") or ""
        error = None
        if len(name) < 2:
            error = "Please enter your name."
        elif not valid_email(email):
            error = "Please enter a valid e-mail address."
        elif request.form.get("password2") is not None and request.form.get("password2") != password:
            error = "Passwords don't match."
        else:
            error = password_problem(password)
        if not error and User.query.filter_by(email=email).first():
            error = "An account with this e-mail already exists. Try signing in."
        if not request.form.get("terms"):
            error = error or "Please accept the terms to continue."
        if error:
            flash(error, "error")
            return render_template("auth/signup.html", name=name, email=email), 400
        user = User(name=name, email=email)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        finish_login(user)
        flash(f"Welcome to Cybok, {name.split()[0]}!", "success")
        return redirect(url_for("main.app_shell"))
    return render_template("auth/signup.html", closed=not open_reg)


@bp.route("/logout", methods=["POST"])
def logout():
    if current_user.is_authenticated:
        Conversation.query.filter_by(user_id=current_user.id, temporary=True).delete()
        db.session.commit()
    session.clear()
    logout_user()
    flash("You have been signed out.", "success")
    return redirect(url_for("auth.login"))


@bp.route("/forgot", methods=["GET", "POST"])
@rate_limit("auth", "RATE_AUTH_PER_5MIN", window=300, methods=("POST",))
def forgot():
    if request.method == "POST":
        email = clean_text(request.form.get("email"), 255).lower()
        user = User.query.filter_by(email=email).first()
        if user and not user.disabled:
            token = _serializer().dumps({"uid": user.id, "v": user.session_version,
                                         "h": (user.password_hash or "")[-12:]})
            link = _external_url("auth.reset", token=token)
            send_mail(user.email, "Reset your Cybok password",
                      f"Hi {user.name},\n\nUse this link to set a new Cybok password (valid for 1 hour):\n{link}\n\n"
                      "If you didn't ask for this, you can ignore this e-mail.\n\n- Cybok")
        msg = "If an account exists for that e-mail, a reset link has been sent."
        if not mail_configured():
            msg += " (E-mail isn't configured on this server, so the link was printed in the server console window.)"
        flash(msg, "success")
        return redirect(url_for("auth.forgot"))
    return render_template("auth/forgot.html")


@bp.route("/reset/<token>", methods=["GET", "POST"])
def reset(token):
    try:
        data = _serializer().loads(token, max_age=3600)
    except SignatureExpired:
        flash("This reset link has expired. Please request a new one.", "error")
        return redirect(url_for("auth.forgot"))
    except BadSignature:
        flash("This reset link is invalid.", "error")
        return redirect(url_for("auth.forgot"))
    user = db.session.get(User, data.get("uid"))
    if not user or user.session_version != data.get("v") or (user.password_hash or "")[-12:] != data.get("h"):
        flash("This reset link was already used or is no longer valid.", "error")
        return redirect(url_for("auth.forgot"))
    if request.method == "POST":
        pw = request.form.get("password") or ""
        error = password_problem(pw)
        if not error and pw != request.form.get("password2"):
            error = "Passwords don't match."
        if error:
            flash(error, "error")
            return render_template("auth/reset.html", token=token), 400
        user.set_password(pw)
        user.session_version += 1  # sign out everywhere
        db.session.commit()
        flash("Your password has been updated. Please sign in.", "success")
        return redirect(url_for("auth.login"))
    return render_template("auth/reset.html", token=token)


# ------------------------------------------------------------------ Google OAuth
@bp.route("/auth/google")
@rate_limit("auth", "RATE_AUTH_PER_5MIN", window=300)
def google_login():
    client = oauth.create_client("google")
    if client is None:
        flash("Google sign-in isn't configured on this server yet.", "error")
        return redirect(url_for("auth.login"))
    session["oauth_nonce"] = secrets.token_urlsafe(16)
    return client.authorize_redirect(_external_url("auth.google_callback"), nonce=session["oauth_nonce"],
                                     prompt="select_account")


@bp.route("/auth/google/callback")
def google_callback():
    client = oauth.create_client("google")
    if client is None:
        return redirect(url_for("auth.login"))
    try:
        token = client.authorize_access_token()
        info = token.get("userinfo") or client.parse_id_token(token, nonce=session.pop("oauth_nonce", None))
    except Exception as exc:
        current_app.logger.warning("Google OAuth failed: %s", exc)
        flash("Google sign-in failed. Please try again.", "error")
        return redirect(url_for("auth.login"))
    if not info or not info.get("email") or not info.get("email_verified", False):
        flash("Your Google account e-mail must be verified.", "error")
        return redirect(url_for("auth.login"))
    email = info["email"].lower()
    user = User.query.filter_by(google_id=info["sub"]).first() or User.query.filter_by(email=email).first()
    if user is None:
        if not (setting_bool("registration_open") or not User.query.count()):
            flash("New registrations are currently closed.", "error")
            return redirect(url_for("auth.login"))
        user = User(name=clean_text(info.get("name"), 120) or email.split("@")[0], email=email)
        db.session.add(user)
    if user.disabled:
        flash("This account has been disabled. Contact the administrator.", "error")
        return redirect(url_for("auth.login"))
    user.google_id = info["sub"]
    if not user.avatar and info.get("picture"):
        user.avatar = info["picture"]
    db.session.commit()
    finish_login(user)
    return redirect(url_for("main.app_shell"))


@bp.route("/account/logout-everywhere", methods=["POST"])
@login_required
def logout_everywhere():
    current_user.session_version += 1
    db.session.commit()
    session.clear()
    logout_user()
    flash("You've been signed out on all devices.", "success")
    return redirect(url_for("auth.login"))
