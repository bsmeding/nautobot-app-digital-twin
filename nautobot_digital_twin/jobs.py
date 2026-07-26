from datetime import datetime, timedelta, timezone

from django.conf import settings
from nautobot.apps.jobs import ChoiceVar, Job, JobButtonReceiver, ObjectVar, register_jobs
from nautobot.dcim.models import Location


def _get_config_source_choices():
    choices = [("empty_config", "Empty config")]
    if getattr(settings, "PLUGINS", None) and "nautobot_golden_config" in settings.PLUGINS:
        choices.append(("intended_config", "Intended config (Golden Config)"))
    return choices


CONFIG_SOURCE_CHOICES = _get_config_source_choices()

_ACTIVE_STATUSES = ["deploying", "deployed", "destroying"]


def _configured_backend_name():
    """Return the plugin-configured backend name (containerlab or eve-ng)."""
    from nautobot_digital_twin.backends import get_configured_backend_name

    return get_configured_backend_name()


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _get_job_user(job):
    """Return the user who initiated the job."""
    user = getattr(job, "user", None)
    if user is not None:
        return user
    job_result = getattr(job, "job_result", None)
    if job_result is not None:
        return getattr(job_result, "user", None)
    return None


def _create_deploying_record(job, location, backend_name):
    """Create a DigitalTwinDeployment record with DEPLOYING status before the backend runs."""
    from nautobot_digital_twin.models import DigitalTwinDeployment
    from nautobot_digital_twin.plugin_config import get_plugin_config

    now = datetime.now(timezone.utc)
    cfg = get_plugin_config()
    minutes = int(cfg.get("DIGITAL_TWIN_AUTO_DESTROY_MINUTES") or 0)
    auto_destroy_at = (now + timedelta(minutes=minutes)) if minutes else None
    deployed_by = _get_job_user(job)
    name = f"{location.name} — {now.isoformat()}"
    deployment = DigitalTwinDeployment.objects.create(
        name=name,
        location=location,
        status=DigitalTwinDeployment.StatusChoices.DEPLOYING,
        backend=backend_name,
        deployed_at=now,
        auto_destroy_at=auto_destroy_at,
        deployed_by=deployed_by,
    )
    return deployment


def _mark_deployment_deployed(deployment):
    """Transition a DEPLOYING record to DEPLOYED."""
    deployment.status = "deployed"
    deployment.save(update_fields=["status"])


def _resolve_location_from_job_button(object_pk, object_model_name):
    """Resolve a Location from Job Button receiver arguments (object detail or list actions)."""
    from django.contrib.contenttypes.models import ContentType

    if "." in object_model_name:
        app_label, model = object_model_name.split(".", 1)
    else:
        app_label, model = "dcim", object_model_name
    ct = ContentType.objects.get_by_natural_key(app_label, model)
    obj = ct.get_object_for_this_type(pk=object_pk)
    if not isinstance(obj, Location):
        raise ValueError(f"Expected Location, got {type(obj).__name__}")
    return obj


def _sync_golden_config_repositories(job):
    """Synchronize Git repositories used by Golden Config before intended generation."""
    import time

    from django.apps import apps

    try:
        GitRepository = apps.get_model("extras", "GitRepository")
    except LookupError:
        job.logger.warning("GitRepository model is not available; skipping Golden Config repository sync.")
        return

    repos_by_pk = {}

    try:
        GoldenConfigSetting = apps.get_model("nautobot_golden_config", "GoldenConfigSetting")
    except LookupError:
        GoldenConfigSetting = None

    if GoldenConfigSetting is not None:
        for settings_obj in GoldenConfigSetting.objects.all():
            for repo_field in ("backup_repository", "intended_repository", "jinja_repository"):
                repo = getattr(settings_obj, repo_field, None)
                if repo is not None:
                    repos_by_pk[repo.pk] = repo

    # Config contexts are not Golden Config setting fields, but templates often depend on them.
    for repo in GitRepository.objects.all():
        provided_contents = getattr(repo, "provided_contents", None) or []
        if any("configcontext" in str(content).lower() for content in provided_contents):
            repos_by_pk[repo.pk] = repo

    if not repos_by_pk:
        job.logger.warning("No Golden Config Git repositories found to sync.")
        return

    user = _get_job_user(job)
    for repo in repos_by_pk.values():
        if not hasattr(repo, "sync"):
            job.logger.warning("Git repository '%s' does not support direct sync; skipping.", repo.name)
            continue
        job.logger.info("Syncing Git repository '%s' before intended config generation...", repo.name)
        sync_result = repo.sync(user=user, dry_run=False)
        job.logger.info("Git repository '%s' sync enqueued (JobResult %s).", repo.name, sync_result.pk)

        poll_interval = 5
        max_wait = 300
        elapsed = 0
        while elapsed < max_wait:
            sync_result.refresh_from_db()
            status = getattr(sync_result, "status", None)
            if status is not None and hasattr(status, "name"):
                status = status.name
            status_str = str(status or "").upper()
            if status_str in ("COMPLETED", "SUCCESS"):
                job.logger.info("Git repository '%s' sync completed successfully.", repo.name)
                break
            if status_str in ("FAILED", "ERROR", "FAILURE"):
                job.logger.failure("Git repository '%s' sync failed. Check JobResult %s.", repo.name, sync_result.pk)
                raise RuntimeError(f"Git repository '{repo.name}' sync failed")
            time.sleep(poll_interval)
            elapsed += poll_interval
        else:
            job.logger.failure("Git repository '%s' sync timed out after %s seconds.", repo.name, max_wait)
            raise TimeoutError(f"Git repository '{repo.name}' sync timed out")


def _run_check_digital_twin_health(job, location):
    """Shared implementation for manual health job and Job Button."""
    from nautobot_digital_twin.backends import get_backend
    from nautobot_digital_twin.models import DigitalTwinDeployment

    deployment = (
        DigitalTwinDeployment.objects.filter(location=location, status__in=_ACTIVE_STATUSES)
        .order_by("-deployed_at")
        .first()
    )
    if not deployment:
        job.logger.warning("No active deployment found for '%s'.", location.name)
        return

    backend_name = deployment.backend or _configured_backend_name()
    backend = get_backend(backend_name)

    ok, message = backend.check_health()
    if not ok:
        job.logger.failure("Digital twin backend '%s' unreachable: %s", backend_name, message)
        return
    job.logger.info("Backend '%s' OK: %s", backend_name, message)

    exit_status, out, err = backend.get_topology_status(location)
    if exit_status == 0:
        job.logger.success("Topology for '%s' is running:\n%s", location.name, out.strip() or "(no output)")
    else:
        job.logger.failure(
            "Could not inspect topology for '%s': %s",
            location.name,
            (err.strip() or out.strip()) or "(no output)",
        )


def _run_validate_digital_twin_connectivity(job, location, ping_count="3"):
    """Shared implementation for manual ping job and Job Button."""
    import re as _re

    from nautobot.dcim.models import Device as _Device

    from nautobot_digital_twin.backends import get_backend
    from nautobot_digital_twin.models import DigitalTwinDeployment

    deployment = (
        DigitalTwinDeployment.objects.filter(location=location, status="deployed").order_by("-deployed_at").first()
    )
    if not deployment:
        job.logger.failure("No active (deployed) digital twin found for '%s'. Deploy first.", location.name)
        return

    backend_name = deployment.backend or _configured_backend_name()
    backend = get_backend(backend_name)
    if not getattr(backend, "supports_connectivity_tests", False):
        job.logger.failure(
            "Backend '%s' does not support connectivity tests (currently containerlab only).",
            backend_name,
        )
        return

    lab_name = _re.sub(r"[^a-z0-9-]", "-", location.name.lower()).strip("-") or "lab"

    devices = list(_Device.objects.filter(location=location).select_related("primary_ip4"))

    testable = []
    for dev in devices:
        if dev.primary_ip4:
            ip_str = str(dev.primary_ip4.address.ip)
            testable.append((dev, ip_str))

    if not testable:
        job.logger.warning(
            "No devices with primary_ip4 at '%s'. Assign primary IPs in Nautobot to enable ping tests.",
            location.name,
        )
        return

    job.logger.info(
        "Starting full-mesh ping test: %d device(s) with IPs at '%s' (lab: %s, pings: %s).",
        len(testable),
        location.name,
        lab_name,
        ping_count,
    )

    passed = 0
    failed = 0
    count = int(ping_count)

    for src_dev, _ in testable:
        src_node = backend._container_name(lab_name, src_dev.name)
        for dst_dev, dst_ip in testable:
            if src_dev.pk == dst_dev.pk:
                continue
            try:
                exit_status, out, err = backend.ping_from_node(src_node, dst_ip, count=count)
            except Exception as e:
                job.logger.warning(
                    "FAIL  %s -> %s (%s): error executing ping: %s",
                    src_dev.name,
                    dst_dev.name,
                    dst_ip,
                    e,
                )
                failed += 1
                continue

            if exit_status == 0:
                job.logger.info("PASS  %s -> %s (%s)", src_dev.name, dst_dev.name, dst_ip)
                passed += 1
            else:
                loss_line = next(
                    (ln.strip() for ln in (out + err).splitlines() if "packet loss" in ln.lower()),
                    err.strip() or out.strip() or "no output",
                )
                job.logger.warning(
                    "FAIL  %s -> %s (%s): %s",
                    src_dev.name,
                    dst_dev.name,
                    dst_ip,
                    loss_line,
                )
                failed += 1

    total = passed + failed
    if total == 0:
        job.logger.warning("No ping tests were executed.")
        return

    if failed == 0:
        job.logger.success("All %d ping test(s) passed.", total)
    else:
        job.logger.failure(
            "%d/%d ping test(s) failed. Check container status and IP reachability.",
            failed,
            total,
        )


def _run_digital_twin_deploy(job, location, backend_name=None, config_source="empty_config"):
    """
    Shared deploy logic. Creates a DEPLOYING record first, then calls the backend.
    On success sets status=DEPLOYED; on failure sets status=FAILED.
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

    if DigitalTwinDeployment.objects.filter(location=location, status__in=_ACTIVE_STATUSES).exists():
        job.logger.failure(
            "Location '%s' already has an active digital twin deployment. Stop it first.",
            location.name,
        )
        return

    cfg = get_plugin_config()

    # User quota check
    max_per_user = int(cfg.get("MAX_DEPLOYMENTS_PER_USER") or 0)
    if max_per_user:
        current_user = _get_job_user(job)
        if current_user:
            user_active = DigitalTwinDeployment.objects.filter(
                deployed_by=current_user,
                status__in=["deploying", "deployed"],
            ).count()
            if user_active >= max_per_user:
                job.logger.failure(
                    "User '%s' has reached the maximum of %d active deployment(s). Stop one first.",
                    current_user.username,
                    max_per_user,
                )
                return

    backend_name = backend_name or _configured_backend_name()
    job.logger.info("Using backend: %s", backend_name)

    deployment = _create_deploying_record(job, location, backend_name)
    job.logger.info("Created deployment record (status=deploying, pk=%s).", deployment.pk)

    try:
        backend = get_backend(backend_name)
        job.logger.info("Generating topology, uploading, and deploying (may take several minutes).")
        result = backend.deploy_site(location, job=job, config_source=config_source)
    except Exception as e:
        job.logger.failure("Deploy failed: %s", e)
        deployment.status = "failed"
        deployment.save(update_fields=["status"])
        raise

    if result is None:
        _mark_deployment_deployed(deployment)
        job.logger.success("Digital Twin deployment triggered for %s.", location.name)
        return

    exit_status, out, err = result
    if out:
        job.logger.info("stdout: %s", out.strip() or "(empty)")
    if err:
        job.logger.warning("stderr: %s", err.strip() or "(empty)")

    if exit_status != 0:
        job.logger.failure("Remote command failed (exit %s). stderr: %s", exit_status, err.strip() if err else "(none)")
        if err and "no such file or directory" in err.lower():
            job.logger.warning(
                "Ensure the topology/lab exists on the backend host "
                "(containerlab: ~/<CONTAINERLAB_REMOTE_TOPOLOGY_DIR>/<site>/<site>.clab.yaml)."
            )
        deployment.status = "failed"
        deployment.save(update_fields=["status"])
        return

    _mark_deployment_deployed(deployment)
    job.logger.success("Digital Twin deployment completed for location '%s'.", location.name)


def _run_digital_twin_destroy(job, location, backend_name=None, mark_destroyed_even_on_failure=False):
    """
    Shared destroy logic. Sets status=DESTROYING during teardown.
    On success sets DESTROYED; on failure sets FAILED (or DESTROYED if mark_destroyed_even_on_failure).
    """
    from nautobot_digital_twin.backends import get_backend
    from nautobot_digital_twin.models import DigitalTwinDeployment

    deployment = (
        DigitalTwinDeployment.objects.filter(location=location, status__in=_ACTIVE_STATUSES)
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
                job.logger.failure("Cannot determine job user. Only the deployer or a superuser may stop it.")
                return
            if current_user.pk != deployment.deployed_by_id and not getattr(current_user, "is_superuser", False):
                job.logger.failure(
                    "Only the user who started this deployment (%s) or a superuser may stop it.",
                    deployment.deployed_by.username if deployment.deployed_by else "unknown",
                )
                return

    backend_name = backend_name or deployment.backend or _configured_backend_name()

    deployment.status = "destroying"
    deployment.save(update_fields=["status"])
    job.logger.info("Set deployment status to 'destroying' (backend: %s).", backend_name)

    try:
        backend = get_backend(backend_name)
        result = backend.destroy_site(location)
    except Exception as e:
        job.logger.failure("Destroy failed: %s", e)
        if mark_destroyed_even_on_failure:
            deployment.status = "destroyed"
            deployment.destroyed_at = datetime.now(timezone.utc)
            deployment.save(update_fields=["status", "destroyed_at"])
        else:
            deployment.status = "failed"
            deployment.save(update_fields=["status"])
        raise

    if result is not None:
        exit_status, out, err = result
        if exit_status != 0:
            job.logger.warning("Destroy command returned exit status %s: %s", exit_status, err or out)
            # If the topology is already gone, treat as success so user can start fresh
            err_lower = (err or out or "").lower()
            lab_already_gone = "no such file" in err_lower or "no such directory" in err_lower
            if not mark_destroyed_even_on_failure and not lab_already_gone:
                deployment.status = "failed"
                deployment.save(update_fields=["status"])
                return

    now = datetime.now(timezone.utc)
    deployment.status = "destroyed"
    deployment.destroyed_at = now
    deployment.save(update_fields=["status", "destroyed_at"])
    job.logger.success("Digital twin for location '%s' stopped.", location.name)


# ---------------------------------------------------------------------------
# Jobs
# ---------------------------------------------------------------------------


class StartDigitalTwinJob(Job):
    """Start a digital twin for a chosen Location (manual run)."""

    class Meta:
        name = "Start Digital Twin (manual)"
        description = "Deploy a digital twin for the selected Location."
        commit_default = True
        soft_time_limit = 600
        time_limit = 660

    location = ObjectVar(model=Location, description="Location to deploy.")
    config_source = ChoiceVar(
        choices=CONFIG_SOURCE_CHOICES,
        default="empty_config",
        description="Config source: empty or Golden Config intended.",
    )

    def run(self, location, config_source, **kwargs):
        _run_digital_twin_deploy(self, location, backend_name=_configured_backend_name(), config_source=config_source)


class StartDigitalTwinJobButtonReceiver(JobButtonReceiver):
    """Start digital twin for the current Location (Job Button on Location detail)."""

    class Meta:
        name = "Start Digital Twin (Job Button)"
        description = "Deploy a digital twin for this Location."
        commit_default = True
        soft_time_limit = 600
        time_limit = 660

    def run(self, object_pk, object_model_name, **kwargs):
        location = _resolve_location_from_job_button(object_pk, object_model_name)
        config_source = (
            "intended_config" if "intended_config" in (c[0] for c in CONFIG_SOURCE_CHOICES) else "empty_config"
        )
        _run_digital_twin_deploy(self, location, config_source=config_source)


class StartDigitalTwinEmptyConfigJob(Job):
    """Start a digital twin with empty startup config, ignoring intended configs."""

    class Meta:
        name = "Start Digital Twin Empty Config (manual)"
        description = "Deploy a digital twin for the selected Location without intended startup configs."
        commit_default = True
        soft_time_limit = 600
        time_limit = 660

    location = ObjectVar(model=Location, description="Location to deploy with empty config.")

    def run(self, location, **kwargs):
        _run_digital_twin_deploy(self, location, backend_name=_configured_backend_name(), config_source="empty_config")


class StartDigitalTwinEmptyConfigJobButtonReceiver(JobButtonReceiver):
    """Start digital twin with empty startup config from a Location Job Button."""

    class Meta:
        name = "Start Digital Twin Empty Config (Job Button)"
        description = "Deploy a digital twin for this Location without intended startup configs."
        commit_default = True
        soft_time_limit = 600
        time_limit = 660

    def run(self, object_pk, object_model_name, **kwargs):
        location = _resolve_location_from_job_button(object_pk, object_model_name)
        _run_digital_twin_deploy(self, location, config_source="empty_config")


class StopDigitalTwinJob(Job):
    """Stop the digital twin for a chosen Location (manual run)."""

    class Meta:
        name = "Stop Digital Twin (manual)"
        description = "Destroy the digital twin for the selected Location."
        commit_default = True
        soft_time_limit = 300
        time_limit = 360

    location = ObjectVar(model=Location, description="Location to stop.")

    def run(self, location, **kwargs):
        _run_digital_twin_destroy(self, location, backend_name=_configured_backend_name())


class StopDigitalTwinJobButtonReceiver(JobButtonReceiver):
    """Stop digital twin for the current Location (Job Button on Location detail)."""

    class Meta:
        name = "Stop Digital Twin (Job Button)"
        description = "Destroy the digital twin for this Location."
        commit_default = True
        soft_time_limit = 300
        time_limit = 360

    def run(self, object_pk, object_model_name, **kwargs):
        location = _resolve_location_from_job_button(object_pk, object_model_name)
        _run_digital_twin_destroy(self, location)


def _run_execute_and_send_intended_config(job, location, backend_name=None):
    """
    Execute Golden Config intended generation, then push configs to the digital twin and reactivate.

    Steps:
    1. Run Golden Config "Generate Intended Configurations" job (enqueue and wait for completion)
    2. Push intended configs to the backend (upload, copy into containers)
    3. Reactivate config on each device (platform-specific reload command)
    """
    import time

    from nautobot_digital_twin.backends import get_backend

    if "intended_config" not in (c[0] for c in CONFIG_SOURCE_CHOICES):
        job.logger.failure("Golden Config plugin is not installed; cannot execute and send intended config.")
        return

    backend_name = backend_name or _configured_backend_name()

    # 1. Sync repositories and run Golden Config IntendedJob.
    job.logger.info("Step 1: Syncing Golden Config Git repositories...")
    _sync_golden_config_repositories(job)

    job.logger.info("Step 2: Running Golden Config 'Generate Intended Configurations' job...")
    try:
        from nautobot.extras.models import JobResult

        # JobModel in 2.2+, Job in older versions
        JobOrModel = None
        try:
            from nautobot.extras.models import JobModel

            JobOrModel = JobModel
        except ImportError:
            from nautobot.extras.models import Job

            JobOrModel = Job

        intended_job = JobOrModel.objects.filter(job_class_name="IntendedJob").first()
        if not intended_job:
            intended_job = JobOrModel.objects.filter(
                job_class_name__icontains="Intended",
            ).first()
        if not intended_job and hasattr(JobOrModel, "get_for_class_path"):
            intended_job = JobOrModel.get_for_class_path("nautobot_golden_config.jobs.IntendedJob")
        if not intended_job:
            job.logger.failure(
                "Golden Config 'Generate Intended Configurations' job not found. "
                "Ensure Golden Config is installed and the job is enabled."
            )
            return

        user = _get_job_user(job)
        child_result = JobResult.enqueue_job(
            job_model=intended_job,
            user=user,
            job_kwargs={
                "fail_job_on_task_failure": True,
                "commit_message": f"Digital Twin intended config generation for {location.name}",
            },
        )
        job.logger.info("Intended job enqueued (JobResult %s). Waiting for completion...", child_result.pk)

        # Poll until complete (max ~15 min)
        poll_interval = 5
        max_wait = 900  # 15 min
        elapsed = 0
        while elapsed < max_wait:
            child_result.refresh_from_db()
            status = getattr(child_result, "status", None)
            if status is not None and hasattr(status, "name"):
                status = status.name
            status_str = str(status or "").upper()
            if status_str in ("COMPLETED", "SUCCESS"):
                job.logger.info("Golden Config intended generation completed successfully.")
                break
            if status_str in ("FAILED", "ERROR", "FAILURE"):
                job.logger.failure("Golden Config intended generation failed. Check the job result for details.")
                return
            time.sleep(poll_interval)
            elapsed += poll_interval
            job.logger.info("Waiting for intended config generation... (%ss)", elapsed)
        else:
            job.logger.failure("Golden Config intended generation timed out after %s seconds.", max_wait)
            return

    except ImportError as e:
        job.logger.failure("Could not run Golden Config job: %s", e)
        return
    except Exception as e:
        job.logger.failure("Golden Config intended generation failed: %s", e)
        raise

    # 3. Push intended configs to backend and reactivate.
    job.logger.info("Step 3: Pushing intended configs to digital twin and reactivating...")
    backend = get_backend(backend_name)
    if not getattr(backend, "supports_intended_config", False):
        job.logger.failure("Backend '%s' does not support push intended config.", backend_name)
        return

    try:
        exit_status, out, err = backend.push_intended_config(location, job=job)
    except Exception as e:
        job.logger.failure("Push failed: %s", e)
        raise

    if exit_status != 0:
        job.logger.failure("Push intended config failed: %s", err or out)
        return

    job.logger.success(
        "Execute and Send Intended Config completed for %s: generated configs, pushed to backend, and reactivated.",
        location.name,
    )


def _run_push_intended_config(job, location, backend_name=None):
    """Push intended config to an already running digital twin."""
    from nautobot_digital_twin.backends import get_backend

    if "intended_config" not in (c[0] for c in CONFIG_SOURCE_CHOICES):
        job.logger.failure("Golden Config plugin is not installed; cannot push intended config.")
        return

    backend_name = backend_name or _configured_backend_name()

    backend = get_backend(backend_name)
    if not getattr(backend, "supports_intended_config", False):
        job.logger.failure("Backend '%s' does not support push intended config.", backend_name)
        return

    job.logger.info("Pushing intended config to digital twin for '%s'", location.name)
    try:
        exit_status, out, err = backend.push_intended_config(location, job=job)
    except Exception as e:
        job.logger.failure("Push failed: %s", e)
        raise

    if exit_status != 0:
        job.logger.failure("Push intended config failed: %s", err or out)
        return
    job.logger.success("Intended config pushed to digital twin for %s", location.name)


class PushIntendedConfigJob(Job):
    """Push intended config to an already running digital twin (manual run)."""

    class Meta:
        name = "Push Intended Config to Digital Twin (manual)"
        description = "Push updated intended config from Golden Config to a running digital twin."
        commit_default = True
        soft_time_limit = 300
        time_limit = 360

    location = ObjectVar(
        model=Location,
        description="Location with running digital twin to push config to",
    )

    def run(self, location, **kwargs):
        _run_push_intended_config(self, location, backend_name=_configured_backend_name())


class PushIntendedConfigJobButtonReceiver(JobButtonReceiver):
    """Push intended config to the current Location's digital twin. Use as Job Button on Location detail."""

    class Meta:
        name = "Push Intended Config to Digital Twin (Job Button)"
        description = "Push intended config to this Location's running digital twin."
        commit_default = True
        soft_time_limit = 300
        time_limit = 360

    def run(self, object_pk, object_model_name, **kwargs):
        from django.contrib.contenttypes.models import ContentType

        ct = ContentType.objects.get_by_natural_key(
            *object_model_name.split(".", 1) if "." in object_model_name else ("dcim", object_model_name)
        )
        location = ct.get_object_for_this_type(pk=object_pk)
        if not isinstance(location, Location):
            self.logger.error("Job Button expects a Location, got %s", type(location).__name__)
            raise ValueError(f"Expected Location, got {type(location).__name__}")
        _run_push_intended_config(self, location)


class ExecuteAndSendIntendedConfigJob(Job):
    """Execute Golden Config intended generation, then push and reactivate on digital twin (manual run)."""

    class Meta:
        name = "Execute and Send Intended Config (manual)"
        description = (
            "Run Golden Config 'Generate Intended Configurations', then push configs to the digital twin "
            "and reactivate on each device."
        )
        commit_default = True
        soft_time_limit = 600  # 15 min for GC + push
        time_limit = 660

    location = ObjectVar(
        model=Location,
        description="Location with running digital twin",
    )

    def run(self, location, **kwargs):
        _run_execute_and_send_intended_config(self, location, backend_name=_configured_backend_name())


class ExecuteAndSendIntendedConfigJobButtonReceiver(JobButtonReceiver):
    """Execute Golden Config intended, push to digital twin, and reactivate. Use as Job Button on Location detail."""

    class Meta:
        name = "Execute and Send Intended Config (Job Button)"
        description = (
            "Run Golden Config to generate intended configs, push them to this Location's digital twin, "
            "and reactivate the new config on each device."
        )
        commit_default = True
        soft_time_limit = 600
        time_limit = 660

    def run(self, object_pk, object_model_name, **kwargs):
        from django.contrib.contenttypes.models import ContentType

        ct = ContentType.objects.get_by_natural_key(
            *object_model_name.split(".", 1) if "." in object_model_name else ("dcim", object_model_name)
        )
        location = ct.get_object_for_this_type(pk=object_pk)
        if not isinstance(location, Location):
            self.logger.error("Job Button expects a Location, got %s", type(location).__name__)
            raise ValueError(f"Expected Location, got {type(location).__name__}")
        _run_execute_and_send_intended_config(self, location)


class RedeployDigitalTwinJob(Job):
    """
    Re-run deploy for an existing active deployment.
    Re-reads Nautobot DCIM data and regenerates the topology; useful after adding/removing devices.
    Does NOT create a new deployment record — it updates the existing one's deployed_at timestamp.
    """

    class Meta:
        name = "Redeploy Digital Twin (update existing)"
        description = (
            "Regenerate topology and re-deploy an active digital twin. "
            "Use after adding/removing devices or cables in Nautobot."
        )
        commit_default = True
        soft_time_limit = 600
        time_limit = 660

    location = ObjectVar(model=Location, description="Location with an active deployment to update.")
    config_source = ChoiceVar(
        choices=CONFIG_SOURCE_CHOICES, default="empty_config", description="Config source for the redeployed nodes."
    )

    def run(self, location, config_source, **kwargs):
        from nautobot_digital_twin.backends import get_backend
        from nautobot_digital_twin.models import DigitalTwinDeployment

        deployment = (
            DigitalTwinDeployment.objects.filter(location=location, status="deployed").order_by("-deployed_at").first()
        )
        if not deployment:
            self.logger.failure(
                "No active (deployed) digital twin found for '%s'. Use Start Digital Twin instead.",
                location.name,
            )
            return

        backend_name = deployment.backend or _configured_backend_name()
        self.logger.info("Redeploying digital twin for '%s' (backend: %s).", location.name, backend_name)
        try:
            backend = get_backend(backend_name)
            result = backend.deploy_site(location, job=self, config_source=config_source)
        except Exception as e:
            self.logger.failure("Redeploy failed: %s", e)
            raise

        if result is None:
            self.logger.success("Redeployment triggered for '%s'.", location.name)
            deployment.deployed_at = datetime.now(timezone.utc)
            deployment.save(update_fields=["deployed_at"])
            return

        exit_status, out, err = result
        if out:
            self.logger.info("stdout: %s", out.strip())
        if err:
            self.logger.warning("stderr: %s", err.strip())

        if exit_status == 0:
            deployment.deployed_at = datetime.now(timezone.utc)
            deployment.save(update_fields=["deployed_at"])
            self.logger.success("Redeployment completed for '%s'.", location.name)
        else:
            self.logger.failure("Redeployment failed (exit %s).", exit_status)


class CheckDigitalTwinHealthJob(Job):
    """
    Check whether a deployed digital twin is actually running on the configured backend.
    """

    class Meta:
        name = "Check Digital Twin Health"
        description = "Inspect the running topology for this Location on the configured backend."
        commit_default = False
        soft_time_limit = 120
        time_limit = 150

    location = ObjectVar(model=Location, description="Location to check.")

    def run(self, location, **kwargs):
        _run_check_digital_twin_health(self, location)


class CheckDigitalTwinHealthJobButtonReceiver(JobButtonReceiver):
    """Run health check for the Location opened from a Job Button (detail or list)."""

    class Meta:
        name = "Check Digital Twin Health (Job Button)"
        description = "Inspect the running topology for this Location on the configured backend."
        commit_default = False
        soft_time_limit = 120
        time_limit = 150

    def run(self, object_pk, object_model_name, **kwargs):
        location = _resolve_location_from_job_button(object_pk, object_model_name)
        _run_check_digital_twin_health(self, location)


class ValidateDigitalTwinConnectivityJob(Job):
    """
    Full-mesh ping test for a deployed digital twin.
    For every device that has a primary IPv4 address in Nautobot, this job pings all other
    such devices from inside the running containers (via docker exec on the containerlab server).
    Results are logged per pair with pass/fail, and a final summary is reported.
    """

    class Meta:
        name = "Validate Digital Twin Connectivity (ping)"
        description = (
            "Run a full-mesh ping test between all devices in an active digital twin. "
            "Requires each device to have a primary_ip4 in Nautobot. "
            "Uses 'docker exec <container> ping' on the containerlab server."
        )
        commit_default = False
        soft_time_limit = 600
        time_limit = 660

    location = ObjectVar(model=Location, description="Location with an active deployment.")
    ping_count = ChoiceVar(
        choices=[("3", "3"), ("5", "5"), ("10", "10")],
        default="3",
        description="Number of ICMP packets to send per ping test.",
    )

    def run(self, location, ping_count="3", **kwargs):
        _run_validate_digital_twin_connectivity(self, location, ping_count=ping_count)


class ValidateDigitalTwinConnectivityJobButtonReceiver(JobButtonReceiver):
    """Run ping connectivity test for the Location opened from a Job Button (detail or list)."""

    class Meta:
        name = "Validate Digital Twin Connectivity (Job Button)"
        description = (
            "Run a full-mesh ping test between all devices in an active digital twin. "
            "Uses 3 ICMP packets per test (same as manual job default)."
        )
        commit_default = False
        soft_time_limit = 600
        time_limit = 660

    def run(self, object_pk, object_model_name, **kwargs):
        location = _resolve_location_from_job_button(object_pk, object_model_name)
        _run_validate_digital_twin_connectivity(self, location, ping_count="3")


class AutoDestroyExpiredDigitalTwinJob(Job):
    """
    Destroy all digital twin deployments that have passed their auto_destroy_at time.
    Schedule this job periodically (e.g. every 15 minutes via Jobs > Schedules).
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

        now = datetime.now(timezone.utc)
        qs = DigitalTwinDeployment.objects.filter(
            status="deployed",
            auto_destroy_at__isnull=False,
            auto_destroy_at__lte=now,
        )
        count = qs.count()
        if count == 0:
            self.logger.info("No expired deployments to destroy.")
            return
        self.logger.info("Destroying %s expired deployment(s).", count)
        for deployment in qs:
            location = deployment.location
            backend_name = deployment.backend or _configured_backend_name()
            self.logger.info(
                "Auto-destroying '%s' via %s (auto_destroy_at was %s).",
                location.name,
                backend_name,
                deployment.auto_destroy_at,
            )
            try:
                backend = get_backend(backend_name)
                result = backend.destroy_site(location)
                if result is not None and result[0] != 0:
                    self.logger.warning(
                        "Destroy for '%s' returned exit status %s: %s",
                        location.name,
                        result[0],
                        result[2] or result[1],
                    )
            except Exception as e:
                self.logger.warning("Destroy for '%s' failed: %s", location.name, e)
            deployment.status = "destroyed"
            deployment.destroyed_at = now
            deployment.save(update_fields=["status", "destroyed_at"])
        self.logger.success("Marked %s deployment(s) as destroyed.", count)


jobs = [
    StartDigitalTwinJob,
    StartDigitalTwinJobButtonReceiver,
    StartDigitalTwinEmptyConfigJob,
    StartDigitalTwinEmptyConfigJobButtonReceiver,
    StopDigitalTwinJob,
    StopDigitalTwinJobButtonReceiver,
    PushIntendedConfigJob,
    PushIntendedConfigJobButtonReceiver,
    ExecuteAndSendIntendedConfigJob,
    ExecuteAndSendIntendedConfigJobButtonReceiver,
    RedeployDigitalTwinJob,
    CheckDigitalTwinHealthJob,
    CheckDigitalTwinHealthJobButtonReceiver,
    ValidateDigitalTwinConnectivityJob,
    ValidateDigitalTwinConnectivityJobButtonReceiver,
    AutoDestroyExpiredDigitalTwinJob,
]
register_jobs(*jobs)
