"""Signal helpers for nautobot_digital_twin."""

from django.apps import apps as global_apps


def create_default_job_buttons(apps=global_apps):
    """
    Create default Job Button records for Location (Start/Stop Digital Twin) if they don't exist.

    This mirrors the pattern used by nautobot-app-golden-config:
    - Look up Job records by job_class_name
    - Create JobButton records pointing at those Jobs
    - Associate them to the dcim.Location content type

    Safe to call multiple times. Returns (created_count, skipped_no_job).
    """
    Job = apps.get_model("extras", "Job")  # pylint: disable=invalid-name
    JobButton = apps.get_model("extras", "JobButton")  # pylint: disable=invalid-name
    ContentType = apps.get_model("contenttypes", "ContentType")  # pylint: disable=invalid-name
    Location = apps.get_model("dcim", "Location")  # pylint: disable=invalid-name

    created_count = 0
    skipped_no_job = 0

    # Look up the Job records by class name, like Golden Config does.
    try:
        start_job = Job.objects.get(job_class_name="StartDigitalTwinJobButtonReceiver")
    except Job.DoesNotExist:
        start_job = None
        skipped_no_job += 1

    try:
        stop_job = Job.objects.get(job_class_name="StopDigitalTwinJobButtonReceiver")
    except Job.DoesNotExist:
        stop_job = None
        skipped_no_job += 1

    if not start_job and not stop_job:
        return created_count, skipped_no_job

    location_ct = ContentType.objects.get_for_model(Location)

    # Start Digital Twin button
    if start_job:
        jb_start, created = JobButton.objects.get_or_create(
            name="Start Digital Twin",
            defaults={
                "text": "Start Digital Twin",
                "job": start_job,
                "weight": 100,
                "group_name": "Nautobot Digital Twin",
                "button_class": "primary",
                "confirmation": True,
            },
        )
        if created:
            jb_start.content_types.set([location_ct])
            # In newer Nautobot versions JobButton has "enabled"; if present, turn it on.
            if hasattr(jb_start, "enabled"):
                jb_start.enabled = True
                jb_start.save(update_fields=["enabled"])
            created_count += 1

    # Stop Digital Twin button
    if stop_job:
        jb_stop, created = JobButton.objects.get_or_create(
            name="Stop Digital Twin",
            defaults={
                "text": "Stop Digital Twin",
                "job": stop_job,
                "weight": 101,
                "group_name": "Nautobot Digital Twin",
                "button_class": "danger",
                "confirmation": True,
            },
        )
        if created:
            jb_stop.content_types.set([location_ct])
            if hasattr(jb_stop, "enabled"):
                jb_stop.enabled = True
                jb_stop.save(update_fields=["enabled"])
            created_count += 1

    return created_count, skipped_no_job


def post_migrate_create_job_buttons(sender, apps=global_apps, **kwargs):  # pylint: disable=unused-argument
    """
    Callback for nautobot_database_ready -- create JobButton records.

    Connected from NautobotDigitalTwinConfig.ready() using nautobot_database_ready,
    so it runs once the database is ready and Jobs have been synced.
    """
    create_default_job_buttons(apps=apps)

