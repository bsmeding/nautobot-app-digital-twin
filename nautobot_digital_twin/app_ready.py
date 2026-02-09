"""
App ready hook: register jobs and ensure DIGITAL_TWIN_ROOT exists.
Keeps cookiecutter __init__.py minimal by moving logic here.
"""
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)


def run_ready():
    """Called from NautobotDigitalTwinConfig.ready() after super().ready()."""
    # Register this app's jobs (so they appear under Jobs → Jobs).
    try:
        from nautobot.apps.jobs import register_jobs
        import nautobot_digital_twin.jobs as jobs_module  # pylint:disable=import-outside-toplevel

        job_list = getattr(jobs_module, "jobs", [])
        if job_list:
            register_jobs(*job_list)
            logger.info("Registered %s job(s) from nautobot_digital_twin.jobs", len(job_list))
    except Exception as e:  # pragma: no cover
        logger.warning("Could not register nautobot_digital_twin jobs: %s", e)

    # Ensure DIGITAL_TWIN_ROOT exists and is writable (non-fatal: log only so Nautobot always starts)
    from nautobot_digital_twin.plugin_config import get_plugin_config  # pylint:disable=import-outside-toplevel

    cfg = get_plugin_config()
    root_path = Path(cfg.get("DIGITAL_TWIN_ROOT", "/opt/nautobot/digital_twin") or "")

    if not root_path:
        logger.warning("DIGITAL_TWIN_ROOT is empty; digital twin deploy may fail.")
    elif not os.path.exists(root_path):
        try:
            os.makedirs(root_path)
            logger.info("Created digital twin root directory %s", root_path)
        except OSError as e:
            logger.warning("Could not create DIGITAL_TWIN_ROOT %s: %s. Deploy may fail.", root_path, e)
    else:
        logger.info("Digital twin root directory %s already exists", root_path)

    if root_path and os.path.exists(root_path):
        if not os.access(root_path, os.W_OK):
            logger.warning("DIGITAL_TWIN_ROOT %s is not writable; saving topology files may fail.", root_path)
        if not os.access(root_path, os.R_OK):
            logger.warning("DIGITAL_TWIN_ROOT %s is not readable.", root_path)
