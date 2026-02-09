"""
Optional integration with nautobot_golden_config: get intended config content for a device.
Only used when Golden Config plugin is installed and config_source='intended_config'.
"""
import logging

logger = logging.getLogger(__name__)


def get_device_intended_config(device):
    """
    Return the intended config string for a device from Golden Config's Git repo, or None.

    Requires nautobot_golden_config to be installed and the intended repo to be synced.
    """
    try:
        from django.conf import settings
        if "nautobot_golden_config" not in getattr(settings, "PLUGINS", []):
            return None
    except Exception:
        return None

    try:
        from nautobot_golden_config.models import GoldenConfigSetting
        from nautobot.extras.models import GitRepository
        from jinja2 import BaseLoader, Environment
        from django.utils.text import slugify
    except ImportError:
        logger.debug("Golden Config not available for intended config")
        return None

    try:
        settings_obj = GoldenConfigSetting.objects.first()
        repo = getattr(settings_obj, "intended_repository", None) if settings_obj else None
        if not settings_obj or not repo:
            logger.warning("Golden Config: no intended repository configured")
            return None
        repo_path = getattr(repo, "filesystem_path", None) or getattr(repo, "local_path", None)
        if not repo_path:
            logger.warning("Golden Config: intended repo not synced (no filesystem_path)")
            return None
        path_template = getattr(settings_obj, "intended_path_template", None) or "{{ obj.location.name | slugify }}/{{ obj.name }}.cfg"
        env = Environment(loader=BaseLoader())
        env.filters["slugify"] = lambda x: slugify(x) if x else ""
        tpl = env.from_string(path_template)
        rel_path = tpl.render(obj=device)
        import os
        full_path = os.path.join(repo_path, rel_path)
        if not os.path.isfile(full_path):
            logger.debug("Intended config file not found: %s", full_path)
            return None
        with open(full_path, "r", encoding="utf-8", errors="replace") as f:
            return f.read()
    except Exception as e:
        logger.warning("Could not get intended config for %s: %s", device.name, e)
        return None
