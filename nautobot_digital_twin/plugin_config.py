"""
Digital Twin plugin config helpers (no import of app package to avoid circular imports).
"""
from django.apps import apps
from django.conf import settings


def get_plugin_config():
    """Return merged plugin config (default_settings + PLUGINS_CONFIG)."""
    app_config = apps.get_app_config("nautobot_digital_twin")
    defaults = getattr(app_config, "default_settings", {}) or {}
    user = settings.PLUGINS_CONFIG.get("nautobot_digital_twin", {}) or {}
    return {**defaults, **user}


def show_digital_twin_button(location):
    """
    Return True if the Digital Twin Start/Stop button should be shown for this location.
    Uses LOCATION_TYPE_NAME (default "Site"); matching is by location_type.name (case-insensitive).
    """
    if location is None or not hasattr(location, "location_type"):
        return False
    cfg = get_plugin_config()
    name = (cfg.get("LOCATION_TYPE_NAME") or "Site").strip()
    return location.location_type.name.strip().lower() == name.lower()
