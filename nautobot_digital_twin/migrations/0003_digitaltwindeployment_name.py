# Add human-readable deployment name (deployment ID) for history

from django.db import migrations, models


def set_deployment_names(apps, schema_editor):
    """Set name for existing deployments: 'LocationName — deployed_at'."""
    DigitalTwinDeployment = apps.get_model("nautobot_digital_twin", "DigitalTwinDeployment")
    seen = set()
    for d in DigitalTwinDeployment.objects.order_by("deployed_at"):
        base = f"{d.location.name} — {d.deployed_at.isoformat()}"
        name = base
        i = 0
        while name in seen:
            i += 1
            name = f"{base} #{i}"
        seen.add(name)
        d.name = name
        d.save()


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("nautobot_digital_twin", "0002_digital_twin_deployment"),
    ]

    operations = [
        migrations.AddField(
            model_name="digitaltwindeployment",
            name="name",
            field=models.CharField(
                help_text="Human-readable deployment ID for history (e.g. SiteName — 2026-02-08 12:00:00).",
                max_length=255,
                null=True,
                unique=True,
            ),
        ),
        migrations.RunPython(set_deployment_names, noop_reverse),
        migrations.AlterField(
            model_name="digitaltwindeployment",
            name="name",
            field=models.CharField(
                help_text="Human-readable deployment ID for history (e.g. SiteName — 2026-02-08 12:00:00).",
                max_length=255,
                unique=True,
            ),
        ),
    ]
