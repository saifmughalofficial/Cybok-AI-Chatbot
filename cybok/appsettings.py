"""Key/value system settings stored in the database (editable from the admin panel)."""
from .extensions import db
from .models import AppSetting

DEFAULTS = {
    # The single source of truth for Cybok's official creation date (YYYY-MM-DD, empty = not configured).
    "creation_date": "",
    "registration_open": "1",
    "max_upload_mb": "20",
    "system_prompt_extra": "",
    "image_provider": "flux-krea",  # falls back to Pollinations when HF_TOKEN is missing or out of credits
    "image_model": "flux",
    "hf_image_model": "black-forest-labs/FLUX.1-schnell",
    "default_model": "",
    "maintenance_message": "",
}


def get_setting(key):
    row = db.session.get(AppSetting, key)
    if row is None:
        return DEFAULTS.get(key, "")
    return row.value or ""


def set_setting(key, value):
    row = db.session.get(AppSetting, key)
    if row is None:
        row = AppSetting(key=key)
        db.session.add(row)
    row.value = "" if value is None else str(value)


def all_settings():
    data = dict(DEFAULTS)
    for row in AppSetting.query.all():
        data[row.key] = row.value or ""
    return data


def setting_bool(key):
    return get_setting(key).strip().lower() in {"1", "true", "yes", "on"}
