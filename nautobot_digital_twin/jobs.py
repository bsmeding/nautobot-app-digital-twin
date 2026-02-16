from datetime import datetime, timedelta, timezone

from django.conf import settings
from nautobot.apps.jobs import Job, JobButtonReceiver, ObjectVar, ChoiceVar, register_jobs
from nautobot.dcim.models import Location

from nautobot_digital_twin.backends import get_available_backend_names

# Config source choices: add "intended_config" only when Golden Config plugin is installed
def _get_config_source_choices():
    choices = [("empty_config", "Empty config")]
    if getattr(settings, "PLUGINS", None) and "nautobot_golden_config" in settings.PLUGINS:
        choices.append(("intended_config", "Intended config (Golden Config)"))
    return choices


CONFIG_SOURCE_CHOICES = _get_config_source_choices()


def _run_digital_twin_deploy(job, location, backend_name=None, config_source="empty_config"):
    """Shared logic: validate location type and call backend deploy.

    backend_name: if set, use this backend; otherwise use BACKEND from config.
    config_source: 'empty_config' or 'intended_config' (only when Golden Config is installed).
    """
    from nautobot_digital_twin.backends import get_backend
    from nautobot_digital_twin.models import DigitalTwinDeployment
    from nautobot_digital_twin.plugin_config import get_plugin_config
    from nautobot_digital_twin.utils import show_digital_twin_button

    job.logger.info("Starting Digital Twin deploy for location '%s' (%s)", location.name, location.pk)

    if not show_digital_twin_button(location):
        job.logger.warning(
            "Location type '%s' is not enabled for Digital Twin (see LOCATION_TYPE_NAME in plugin config).",
            location.location_type.name,
        )
        return

    if DigitalTwinDeployment.objects.filter(
        location=location, status=DigitalTwinDeployment.StatusChoices.DEPLOYED
    ).exists():
        job.logger.failure(
            "Location '%s' already has an active digital twin deployment. Stop it first or wait for auto-destroy.",
            location.name,
        )
        return

    if backend_name is None:
        cfg = get_plugin_config()
        backend_name = cfg.get("BACKEND", "containerlab")
    job.logger.info("Using backend: %s", backend_name)

    try:
        backend = get_backend(backend_name)
        job.logger.info("Backend obtained; generating topology, uploading, then deploying (may take several minutes).")
        result = backend.deploy_site(location, job=job, config_source=config_source)
    except Exception as e:
        job.logger.failure("Deploy failed: %s", e)
        raise

    if result is None:
        job.logger.success("Digital Twin deployment triggered for %s", location.name)
        _record_deployment_created(job, location, backend_name)
        return

    exit_status, out, err = result
    if out:
        job.logger.info("stdout: %s", out.strip() or "(empty)")
    if err:
        job.logger.warning("stderr: %s", err.strip() or "(empty)")

    if exit_status != 0:
        job.logger.failure(
            "Remote command failed with exit status %s. stderr: %s",
            exit_status,
            err.strip() if err else "(none)",
        )
        if err and "no such file or directory" in err.lower():
            job.logger.warning(
                "Ensure the topology file exists on the containerlab server at "
                "~/<CONTAINERLAB_REMOTE_TOPOLOGY_DIR>/<site>/<site>.clab.yaml (e.g. ~/nautobot/%s/%s.clab.yaml).",
                location.name,
                location.name,
            )
        return

    job.logger.success("Digital Twin deployment completed for location '%s'", location.name)
    _record_deployment_created(job, location, backend_name)


def _get_job_user(job):
    """Return the user who initiated the job (from job.user or job_result.user)."""
    user = getattr(job, "user", None)
    if user is not None:
        return user
    job_result = getattr(job, "job_result", None)
    if job_result is not None and hasattr(job_result, "user"):
        return getattr(job_result, "user", None)
    return None


def _record_deployment_created(job, location, backend_name):
    """Create a DigitalTwinDeployment record after successful deploy."""
    from nautobot_digital_twin.models import DigitalTwinDeployment
    from nautobot_digital_twin.plugin_config import get_plugin_config

    now = datetime.now(timezone.utc)
    cfg = get_plugin_config()
    minutes = int(cfg.get("DIGITAL_TWIN_AUTO_DESTROY_MINUTES") or 0)
    auto_destroy_at = (now + timedelta(minutes=minutes)) if minutes else None
    deployed_by = _get_job_user(job)
    deployment_name = f"{location.name} — {now.isoformat()}"
    DigitalTwinDeployment.objects.create(
        name=deployment_name,
        location=location,
        status=DigitalTwinDeployment.StatusChoices.DEPLOYED,
        backend=backend_name,
        deployed_at=now,
        auto_destroy_at=auto_destroy_at,
        deployed_by=deployed_by,
    )


def _run_digital_twin_destroy(job, location, backend_name=None, mark_destroyed_even_on_failure=False):
    """Stop digital twin for location: call backend destroy and mark deployment destroyed.

    If mark_destroyed_even_on_failure is True (e.g. for auto-destroy), we still mark the
    deployment destroyed so we don't retry forever.
    When not auto-destroy, only the user who deployed or a superuser may stop the deployment.
    """
    from nautobot_digital_twin.backends import get_backend
    from nautobot_digital_twin.models import DigitalTwinDeployment
    from nautobot_digital_twin.plugin_config import get_plugin_config

    deployment = (
        DigitalTwinDeployment.objects.filter(
            location=location, status=DigitalTwinDeployment.StatusChoices.DEPLOYED
        )
        .order_by("-deployed_at")
        .first()
    )
    if not deployment:
        job.logger.warning("No active digital twin deployment found for location '%s'.", location.name)
        return

    if not mark_destroyed_even_on_failure:
        current_user = _get_job_user(job)
        if deployment.deployed_by_id is not None:
            if current_user is None:
                job.logger.failure(
                    "Cannot determine who is running this job. Only the user who started the deployment or a superuser may stop it."
                )
                return
            if current_user.pk != deployment.deployed_by_id and not getattr(current_user, "is_superuser", False):
                job.logger.failure(
                    "Only the user who started this deployment (%s) or a superuser may stop it.",
                    deployment.deployed_by.username if deployment.deployed_by else "unknown",
                )
                return

    if backend_name is None:
        cfg = get_plugin_config()
        backend_name = cfg.get("BACKEND", "containerlab")
    try:
        backend = get_backend(backend_name)
        result = backend.destroy_site(location)
    except Exception as e:
        job.logger.failure("Destroy failed: %s", e)
        if mark_destroyed_even_on_failure:
            deployment.status = DigitalTwinDeployment.StatusChoices.DESTROYED
            deployment.destroyed_at = datetime.now(timezone.utc)
            deployment.save()
        raise

    if result is not None:
        exit_status, out, err = result
        if exit_status != 0:
            job.logger.warning("Destroy command returned exit status %s: %s", exit_status, err or out)
            if not mark_destroyed_even_on_failure:
                return

    now = datetime.now(timezone.utc)
    deployment.status = DigitalTwinDeployment.StatusChoices.DESTROYED
    deployment.destroyed_at = now
    deployment.save()
    job.logger.success("Digital twin for location '%s' stopped and deployment record updated.", location.name)


# Backend dropdown for manual job: list of (value, label), first is default
_backend_names = get_available_backend_names()
BACKEND_CHOICES = [(n, n) for n in _backend_names]
DEFAULT_BACKEND = BACKEND_CHOICES[0][0] if BACKEND_CHOICES else "containerlab"


class StartDigitalTwinJob(Job):
    """Start a digital twin for a chosen Location. Use from Jobs → Jobs (manual run)."""

    class Meta:
        name = "Start Digital Twin (manual)"
        description = "Deploy a digital twin for the selected Location."
        commit_default = True
        soft_time_limit = 600   # 10 min: raise SoftTimeLimitExceeded so job can fail cleanly
        time_limit = 660        # 11 min: hard kill if still running

    backend = ChoiceVar(
        choices=BACKEND_CHOICES,
        default=DEFAULT_BACKEND,
        description="Backend to use for deployment (e.g. containerlab).",
    )
    location = ObjectVar(
        model=Location,
        description="Location to start the digital twin for",
    )
    config_source = ChoiceVar(
        choices=CONFIG_SOURCE_CHOICES,
        default="empty_config",
        description="Config to load: empty or intended (from Golden Config, if installed).",
    )

    def run(self, location, backend, config_source, **kwargs):
        _run_digital_twin_deploy(self, location, backend_name=backend, config_source=config_source)


class StartDigitalTwinJobButtonReceiver(JobButtonReceiver):
    """Start digital twin for the current Location. Use as a Job Button on Location detail.

    JobButtonReceiver only receives object_pk and object_model_name from the button;
    do not add ObjectVar/ChoiceVar or the job will not start when the button is clicked.
    """

    class Meta:
        name = "Start Digital Twin (Job Button)"
        description = "Deploy a digital twin for this Location (receives Location from button)."
        commit_default = True
        soft_time_limit = 600
        time_limit = 660

    def run(self, object_pk, object_model_name, **kwargs):
        """Resolve Location from object_pk/object_model_name and run deploy (empty config)."""
        from django.contrib.contenttypes.models import ContentType

        ct = ContentType.objects.get_by_natural_key(
            *object_model_name.split(".", 1)
            if "." in object_model_name
            else ("dcim", object_model_name)
        )
        location = ct.get_object_for_this_type(pk=object_pk)
        if not isinstance(location, Location):
            self.logger.error("Job Button expects a Location, got %s", type(location).__name__)
            raise ValueError(f"Expected Location, got {type(location).__name__}")
        # Use intended config when Golden Config is available; otherwise empty
        config_source = "intended_config" if "intended_config" in (c[0] for c in CONFIG_SOURCE_CHOICES) else "empty_config"
        _run_digital_twin_deploy(self, location, config_source=config_source)


class StopDigitalTwinJob(Job):
    """Stop the digital twin for a chosen Location (manual run)."""

    class Meta:
        name = "Stop Digital Twin (manual)"
        description = "Destroy the digital twin for the selected Location and mark deployment as stopped."
        commit_default = True
        soft_time_limit = 300
        time_limit = 360

    backend = ChoiceVar(
        choices=BACKEND_CHOICES,
        default=DEFAULT_BACKEND,
        description="Backend used for the deployment (must match the one used to start).",
    )
    location = ObjectVar(
        model=Location,
        description="Location to stop the digital twin for",
    )

    def run(self, location, backend, **kwargs):
        _run_digital_twin_destroy(self, location, backend_name=backend)


class StopDigitalTwinJobButtonReceiver(JobButtonReceiver):
    """Stop digital twin for the current Location. Use as a Job Button on Location detail.

    JobButtonReceiver only receives object_pk and object_model_name from the button;
    do not add ObjectVar or the job will not start when the button is clicked.
    """

    class Meta:
        name = "Stop Digital Twin (Job Button)"
        description = "Destroy the digital twin for this Location (receives Location from button)."
        commit_default = True
        soft_time_limit = 300
        time_limit = 360

    def run(self, object_pk, object_model_name, **kwargs):
        """Resolve Location from object_pk/object_model_name and run destroy."""
        from django.contrib.contenttypes.models import ContentType

        ct = ContentType.objects.get_by_natural_key(
            *object_model_name.split(".", 1)
            if "." in object_model_name
            else ("dcim", object_model_name)
        )
        location = ct.get_object_for_this_type(pk=object_pk)
        if not isinstance(location, Location):
            self.logger.error("Job Button expects a Location, got %s", type(location).__name__)
            raise ValueError(f"Expected Location, got {type(location).__name__}")
        _run_digital_twin_destroy(self, location)


class AutoDestroyExpiredDigitalTwinJob(Job):
    """Destroy all digital twin deployments that have passed their auto_destroy_at time.

    Schedule this job periodically (e.g. every 15 minutes via Jobs > Schedules) so that
    deployments are torn down after DIGITAL_TWIN_AUTO_DESTROY_MINUTES.
    """

    class Meta:
        name = "Auto-destroy expired Digital Twin deployments"
        description = (
            "Find deployments with auto_destroy_at in the past, run backend destroy, "
            "and mark them destroyed. Schedule this job (e.g. */15 * * * *) to enable auto-destroy."
        )
        commit_default = True
        soft_time_limit = 600
        time_limit = 660

    def run(self, **kwargs):
        from nautobot_digital_twin.backends import get_backend
        from nautobot_digital_twin.models import DigitalTwinDeployment
        from nautobot_digital_twin.plugin_config import get_plugin_config

        now = datetime.now(timezone.utc)
        qs = DigitalTwinDeployment.objects.filter(
            status=DigitalTwinDeployment.StatusChoices.DEPLOYED,
            auto_destroy_at__isnull=False,
            auto_destroy_at__lte=now,
        )
        count = qs.count()
        if count == 0:
            self.logger.info("No expired deployments to destroy.")
            return
        self.logger.info("Destroying %s expired deployment(s).", count)
        cfg = get_plugin_config()
        backend_name = cfg.get("BACKEND", "containerlab")
        backend = get_backend(backend_name)
        for deployment in qs:
            location = deployment.location
            self.logger.info("Auto-destroying deployment for location '%s' (auto_destroy_at was %s).", location.name, deployment.auto_destroy_at)
            try:
                result = backend.destroy_site(location)
                if result is not None and result[0] != 0:
                    self.logger.warning("Destroy for %s returned exit status %s: %s", location.name, result[0], result[2] or result[1])
            except Exception as e:
                self.logger.warning("Destroy for %s failed: %s", location.name, e)
            deployment.status = DigitalTwinDeployment.StatusChoices.DESTROYED
            deployment.destroyed_at = now
            deployment.save()
        self.logger.success("Marked %s deployment(s) as destroyed.", count)


jobs = [
    StartDigitalTwinJob,
    StartDigitalTwinJobButtonReceiver,
    StopDigitalTwinJob,
    StopDigitalTwinJobButtonReceiver,
    AutoDestroyExpiredDigitalTwinJob,
]
register_jobs(*jobs)
