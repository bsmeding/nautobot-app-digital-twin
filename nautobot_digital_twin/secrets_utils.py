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
