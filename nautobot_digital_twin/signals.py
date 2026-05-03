"""Signal helpers for nautobot_digital_twin."""

from django.apps import apps as global_apps

# Job buttons created on Location detail pages.
# weight determines left-to-right order in the button group.
_JOB_BUTTON_SPECS = [
    {
        "job_class_name": "StartDigitalTwinJobButtonReceiver",
        "button_name": "Start Digital Twin",
        "text": "Start Digital Twin",
        "weight": 100,
        "button_class": "primary",
        "confirmation": True,
    },
    {
        "job_class_name": "StartDigitalTwinEmptyConfigJobButtonReceiver",
        "button_name": "Start Digital Twin Empty Config",
        "text": "Start Empty Config",
        "weight": 101,
        "button_class": "default",
        "confirmation": True,
    },
    {
        "job_class_name": "StopDigitalTwinJobButtonReceiver",
        "button_name": "Stop Digital Twin",
        "text": "Stop Digital Twin",
        "weight": 102,
        "button_class": "danger",
        "confirmation": True,
    },
    {
        "job_class_name": "CheckDigitalTwinHealthJobButtonReceiver",
        "button_name": "Check Digital Twin Health",
        "text": "Check Health",
        "weight": 103,
        "button_class": "default",
        "confirmation": False,
    },
    {
        "job_class_name": "ValidateDigitalTwinConnectivityJobButtonReceiver",
        "button_name": "Validate Digital Twin Connectivity",
        "text": "Ping Test",
        "weight": 104,
        "button_class": "info",
        "confirmation": True,
    },
    {
        "job_class_name": "PushIntendedConfigJobButtonReceiver",
        "button_name": "Push Intended Config",
        "text": "Push Intended Config",
        "weight": 105,
        "button_class": "info",
        "confirmation": True,
    },
    {
        "job_class_name": "ExecuteAndSendIntendedConfigJobButtonReceiver",
        "button_name": "Execute and Send Intended Config",
        "text": "Execute and Send Intended Config",
        "weight": 106,
        "button_class": "success",
        "confirmation": True,
    },
]


def create_default_job_buttons(apps=global_apps):
    """
    Create default Job Button records for Location (Start/Stop/HealthCheck/PingTest Digital Twin)
    if they don't already exist. Safe to call multiple times.

    Returns (created_count, skipped_no_job).
    """
    Job = apps.get_model("extras", "Job")  # pylint: disable=invalid-name
    JobButton = apps.get_model("extras", "JobButton")  # pylint: disable=invalid-name
    ContentType = apps.get_model("contenttypes", "ContentType")  # pylint: disable=invalid-name
    Location = apps.get_model("dcim", "Location")  # pylint: disable=invalid-name

    location_ct = ContentType.objects.get_for_model(Location)
    created_count = 0
    skipped_no_job = 0

    for spec in _JOB_BUTTON_SPECS:
        try:
            job_record = Job.objects.get(job_class_name=spec["job_class_name"])
        except Job.DoesNotExist:
            skipped_no_job += 1
            continue

        jb, created = JobButton.objects.get_or_create(
            name=spec["button_name"],
            defaults={
                "text": spec["text"],
                "job": job_record,
                "weight": spec["weight"],
                "group_name": "Nautobot Digital Twin",
                "button_class": spec["button_class"],
                "confirmation": spec["confirmation"],
            },
        )
        # Re-sync on every run so existing buttons pick up new JobButtonReceiver classes after upgrades.
        jb.text = spec["text"]
        jb.job = job_record
        jb.weight = spec["weight"]
        jb.group_name = "Nautobot Digital Twin"
        jb.button_class = spec["button_class"]
        jb.confirmation = spec["confirmation"]
        jb.save()
        jb.content_types.set([location_ct])
        if hasattr(jb, "enabled"):
            jb.enabled = True
            jb.save(update_fields=["enabled"])
        if created:
            created_count += 1

    return created_count, skipped_no_job


def post_migrate_create_job_buttons(sender, apps=global_apps, **kwargs):  # pylint: disable=unused-argument
    """
    Callback for nautobot_database_ready — create JobButton records.
    Connected from NautobotDigitalTwinConfig.ready() using nautobot_database_ready.
    """
    create_default_job_buttons(apps=apps)
