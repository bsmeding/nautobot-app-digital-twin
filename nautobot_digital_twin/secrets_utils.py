"""
Resolve credentials from Nautobot Secrets Groups.

Used for CONTAINERLAB_SSH_CREDENTIALS_SECRETS_GROUP and DIGITAL_TWIN_FALLBACK_AUTH_SECRETS_GROUP.
"""

import logging

logger = logging.getLogger(__name__)


def get_credentials_from_secrets_group(secrets_group_name, access_type, obj=None):
    """
    Get username and password from a Nautobot Secrets Group.

    Args:
        secrets_group_name: Name of the Secrets Group (empty string = not configured).
        access_type: Access type for the secrets (e.g. TYPE_SSH, TYPE_GENERIC).
        obj: Optional context object for templated secret parameters.

    Returns:
        Tuple (username, password) if successful, None if not configured or lookup failed.
    """
    if not (secrets_group_name and str(secrets_group_name).strip()):
        return None

    try:
        from nautobot.extras.models import SecretsGroup
        from nautobot.extras.choices import (
            SecretsGroupAccessTypeChoices,
            SecretsGroupSecretTypeChoices,
        )
    except ImportError as e:
        logger.warning("Cannot import Nautobot Secrets: %s", e)
        return None

    try:
        group = SecretsGroup.objects.get(name=secrets_group_name.strip())
    except SecretsGroup.DoesNotExist:
        logger.warning("Secrets Group '%s' not found", secrets_group_name)
        return None

    try:
        username = group.get_secret_value(
            access_type=access_type,
            secret_type=SecretsGroupSecretTypeChoices.TYPE_USERNAME,
            obj=obj,
        )
        password = group.get_secret_value(
            access_type=access_type,
            secret_type=SecretsGroupSecretTypeChoices.TYPE_PASSWORD,
            obj=obj,
        )
        if username is not None and password is not None:
            return (str(username), str(password))
        logger.warning(
            "Secrets Group '%s' missing Username or Password for access type %s",
            secrets_group_name,
            access_type,
        )
        return None
    except Exception as e:
        logger.warning("Failed to get credentials from Secrets Group '%s': %s", secrets_group_name, e)
        return None


def get_fallback_auth_credentials():
    """
    Get username/password for PLATFORM_ADD_CONFIG_LINES (when using {username}/{password} placeholders).

    Uses DIGITAL_TWIN_FALLBACK_AUTH_SECRETS_GROUP (access type Generic) if set,
    else returns ("admin", "admin") for lab/demo use.

    Returns:
        Tuple (username, password). Never None.
    """
    from nautobot_digital_twin.plugin_config import get_plugin_config

    cfg = get_plugin_config()
    secrets_group = (cfg.get("DIGITAL_TWIN_FALLBACK_AUTH_SECRETS_GROUP") or "").strip()
    if secrets_group:
        creds = get_credentials_from_secrets_group(secrets_group, "generic")
        if creds:
            return creds
    # Backward compat: DIGITAL_TWIN_DEFAULT_USERNAME/PASSWORD (removed, use Secrets Group)
    username = cfg.get("DIGITAL_TWIN_DEFAULT_USERNAME")
    password = cfg.get("DIGITAL_TWIN_DEFAULT_PASSWORD")
    if username is not None and password is not None:
        return (str(username), str(password))
    return ("admin", "admin")
