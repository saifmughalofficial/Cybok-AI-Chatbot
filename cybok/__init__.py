"""Cybok - Your AI. Your Workspace."""
import logging
import os
from datetime import timedelta

from flask import Flask, jsonify, render_template, request
from werkzeug.exceptions import HTTPException

from .config import INSTANCE_DIR, Config
from .extensions import db, login_manager, oauth
from .security import apply_security_headers, csrf_protect, csrf_token


def create_app(config_object=Config):
    app = Flask(__name__, instance_path=str(INSTANCE_DIR), instance_relative_config=False)
    app.config.from_object(config_object)
    app.permanent_session_lifetime = timedelta(seconds=app.config["PERMANENT_SESSION_LIFETIME"])
    INSTANCE_DIR.mkdir(parents=True, exist_ok=True)
    app.config["UPLOAD_DIR"].mkdir(parents=True, exist_ok=True)

    if app.config["SECRET_KEY"] == "dev-insecure-change-me":
        app.logger.warning("SECRET_KEY is not set - using an insecure development key. Run start.bat / run.py to generate one.")

    if app.config["BEHIND_PROXY"]:
        from werkzeug.middleware.proxy_fix import ProxyFix
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    db.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"
    login_manager.login_message = None
    oauth.init_app(app)
    if app.config["GOOGLE_CLIENT_ID"] and app.config["GOOGLE_CLIENT_SECRET"]:
        oauth.register(
            name="google",
            client_id=app.config["GOOGLE_CLIENT_ID"],
            client_secret=app.config["GOOGLE_CLIENT_SECRET"],
            server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
            client_kwargs={"scope": "openid email profile"},
        )

    from .models import User

    @login_manager.user_loader
    def load_user(token):
        try:
            uid, ver = token.split(":")
            user = db.session.get(User, int(uid))
        except (ValueError, AttributeError):
            return None
        if user and str(user.session_version) == ver and not user.disabled:
            return user
        return None

    from .routes.admin import bp as admin_bp
    from .routes.api import bp as api_bp
    from .routes.auth import bp as auth_bp
    from .routes.main import bp as main_bp
    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(api_bp)
    app.register_blueprint(admin_bp)

    app.before_request(csrf_protect)
    app.after_request(apply_security_headers)

    @app.context_processor
    def inject_globals():
        return {
            "csrf_token": csrf_token,
            "APP_NAME": app.config["APP_NAME"],
            "TAGLINE": app.config["TAGLINE"],
            "CREATOR_NAME": app.config["CREATOR_NAME"],
            "CREATOR_DESCRIPTION": app.config["CREATOR_DESCRIPTION"],
            "VERSION": app.config["VERSION"],
            "google_enabled": bool(app.config["GOOGLE_CLIENT_ID"] and app.config["GOOGLE_CLIENT_SECRET"]),
            "asset_v": app.config["VERSION"] + "-" + str(int(os.path.getmtime(__file__))),
        }

    @app.errorhandler(HTTPException)
    def http_error(err):
        if request.path.startswith("/api/"):
            if err.response is not None:
                return err.response
            return jsonify(error=err.description or err.name), err.code
        return render_template("error.html", code=err.code, title=err.name, message=err.description), err.code

    @app.errorhandler(Exception)
    def server_error(err):
        app.logger.exception("Unhandled error")
        try:
            db.session.rollback()
            from .security import log_error
            log_error("server", f"{request.method} {request.path}: {err!r}")
        except Exception:
            pass
        if request.path.startswith("/api/"):
            return jsonify(error="Something went wrong on our side. Please try again."), 500
        return render_template("error.html", code=500, title="Something went wrong",
                               message="An unexpected error occurred. Please try again."), 500

    with app.app_context():
        init_database()

    return app


def _sqlite_foreign_keys(dbapi_conn, _record):
    cur = dbapi_conn.cursor()
    cur.execute("PRAGMA foreign_keys=ON")
    cur.execute("PRAGMA journal_mode=WAL")
    cur.close()


def init_database():
    from sqlalchemy import event

    from .ai.chat import seed_models
    from .appsettings import get_setting, set_setting
    from .models import AppSetting

    if db.engine.dialect.name == "sqlite":
        event.listen(db.engine, "connect", _sqlite_foreign_keys)
        db.engine.dispose()  # make sure every new connection gets the pragmas
    db.create_all()
    seed_models()
    # Seed the official creation date from .env once; afterwards Admin > System is the source of truth.
    if db.session.get(AppSetting, "creation_date") is None:
        set_setting("creation_date", Config.CYBOK_CREATION_DATE)
    if db.session.get(AppSetting, "max_upload_mb") is None:
        set_setting("max_upload_mb", str(Config.MAX_UPLOAD_MB))
    db.session.commit()
    return get_setting
