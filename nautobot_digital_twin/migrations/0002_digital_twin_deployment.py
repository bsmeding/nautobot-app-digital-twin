# Generated migration for DigitalTwinDeployment model

import django.core.serializers.json
import django.db.models.deletion
from django.db import migrations, models
import nautobot.core.models.fields
import uuid


class Migration(migrations.Migration):

    dependencies = [
        ("nautobot_digital_twin", "0001_initial"),
        # dcim.Location and users.User are provided by Nautobot core (migrated before plugins).
    ]

    operations = [
        migrations.CreateModel(
            name="DigitalTwinDeployment",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False, unique=True)),
                ("created", models.DateTimeField(auto_now_add=True, null=True)),
                ("last_updated", models.DateTimeField(auto_now=True, null=True)),
                ("_custom_field_data", models.JSONField(blank=True, default=dict, encoder=django.core.serializers.json.DjangoJSONEncoder)),
                ("status", models.CharField(choices=[("deployed", "Deployed"), ("destroyed", "Destroyed")], max_length=32)),
                ("backend", models.CharField(default="containerlab", max_length=64)),
                ("deployed_at", models.DateTimeField()),
                ("destroyed_at", models.DateTimeField(blank=True, null=True)),
                ("auto_destroy_at", models.DateTimeField(blank=True, help_text="When to automatically destroy this deployment.", null=True)),
                ("tags", nautobot.core.models.fields.TagsField(through="extras.TaggedItem", to="extras.Tag")),
                ("deployed_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="digital_twin_deployments", to="users.user")),
                ("location", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="digital_twin_deployments", to="dcim.location")),
            ],
            options={
                "ordering": ["-deployed_at"],
                "verbose_name": "Digital Twin Deployment",
                "verbose_name_plural": "Digital Twin Deployments",
            },
        ),
        migrations.AddConstraint(
            model_name="digitaltwindeployment",
            constraint=models.UniqueConstraint(condition=models.Q(("status", "deployed")), fields=("location",), name="unique_active_deployment_per_location"),
        ),
    ]
