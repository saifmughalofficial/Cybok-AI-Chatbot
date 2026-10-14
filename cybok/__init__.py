"""Cybok - Your AI. Your Workspace.

The UI is the Streamlit app in app.py. A bare Flask app object is kept only as the
container for Flask-SQLAlchemy (database session + config); it serves no web pages.
"""
import logging

from flask import Flask

from .config import INSTANCE_DIR, Config
from .extensions import db


def create_app(config_object=Config):
    app = Flask(__name__, instance_path=str(INSTANCE_DIR), instance_relative_config=False)
    app.config.from_object(config_object)
    INSTANCE_DIR.mkdir(parents=True, exist_ok=True)
    app.config["UPLOAD_DIR"].mkdir(parents=True, exist_ok=True)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    db.init_app(app)
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
