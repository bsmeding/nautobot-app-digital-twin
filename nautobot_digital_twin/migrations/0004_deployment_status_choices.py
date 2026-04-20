"""Add DEPLOYING, DESTROYING, FAILED status choices and update unique constraint."""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("nautobot_digital_twin", "0003_digitaltwindeployment_name"),
    ]

    operations = [
        # Widen the status field to accept new choices
        migrations.AlterField(
            model_name="digitaltwindeployment",
            name="status",
            field=models.CharField(
                max_length=32,
                choices=[
                    ("deploying", "Deploying"),
                    ("deployed", "Deployed"),
                    ("destroying", "Destroying"),
                    ("destroyed", "Destroyed"),
                    ("failed", "Failed"),
                ],
            ),
        ),
        # Replace the unique constraint so DEPLOYING and DESTROYING are also exclusive
        migrations.RemoveConstraint(
            model_name="digitaltwindeployment",
            name="unique_active_deployment_per_location",
        ),
        migrations.AddConstraint(
            model_name="digitaltwindeployment",
            constraint=models.UniqueConstraint(
                fields=["location"],
                condition=models.Q(status__in=["deploying", "deployed", "destroying"]),
                name="unique_active_deployment_per_location",
            ),
        ),
    ]
