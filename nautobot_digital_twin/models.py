"""Models for Nautobot Digital Twin."""

# Django imports
from django.conf import settings
from django.db import models

# Nautobot imports
from nautobot.apps.constants import CHARFIELD_MAX_LENGTH
from nautobot.apps.models import PrimaryModel, extras_features


class DigitalTwinDeployment(PrimaryModel):
    """
    Tracks a digital twin deployment per Location.
    One active (status=deployed) deployment per location; auto-destroy after configured time.
    Each Start creates a new record (deployment history); Stop marks that record as destroyed.
    """

    class StatusChoices(models.TextChoices):
        DEPLOYING = "deploying", "Deploying"
        DEPLOYED = "deployed", "Deployed"
        DESTROYING = "destroying", "Destroying"
        DESTROYED = "destroyed", "Destroyed"
        FAILED = "failed", "Failed"

    name = models.CharField(
        max_length=255,
        unique=True,
        help_text="Human-readable deployment ID for history (e.g. SiteName — 2026-02-08 12:00:00).",
    )
    location = models.ForeignKey(
        to="dcim.Location",
        on_delete=models.CASCADE,
        related_name="digital_twin_deployments",
    )
    status = models.CharField(max_length=32, choices=StatusChoices.choices)
    backend = models.CharField(max_length=64, default="containerlab")
    deployed_at = models.DateTimeField()
    destroyed_at = models.DateTimeField(null=True, blank=True)
    auto_destroy_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When to automatically destroy this deployment.",
    )
    deployed_by = models.ForeignKey(
        to=settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="digital_twin_deployments",
    )

    class Meta:
        ordering = ["-deployed_at"]
        verbose_name = "Digital Twin Deployment"
        verbose_name_plural = "Digital Twin Deployments"
        constraints = [
            models.UniqueConstraint(
                fields=["location"],
                condition=models.Q(status__in=["deploying", "deployed", "destroying"]),
                name="unique_active_deployment_per_location",
            ),
        ]

    def __str__(self):
        return self.name

    @property
    def remote_topology_path(self):
        """
        Path to the topology file on the remote containerlab host for this deployment.

        Mirrors the logic in the containerlab backend:
        ~/{CONTAINERLAB_REMOTE_TOPOLOGY_DIR}/{site.name}/{site.name}.clab.yaml
        """
        from nautobot_digital_twin.plugin_config import get_plugin_config  # pylint:disable=import-outside-toplevel

        cfg = get_plugin_config()
        subdir = (cfg.get("CONTAINERLAB_REMOTE_TOPOLOGY_DIR") or "nautobot").strip("/")
        return f"~/{subdir}/{self.location.name}/{self.location.name}.clab.yaml"

    @property
    def mermaid_topology(self):
        """
        Mermaid graph description of the current Location topology.

        Uses the same devices/cables as the containerlab topology builder,
        but simplified to device-to-device edges for easy visualization.
        """
        from nautobot_digital_twin.topology import (  # pylint:disable=import-outside-toplevel
            build_mermaid_topology,
        )

        return build_mermaid_topology(self.location)


# If you want to choose a specific model to overload in your class declaration, please reference the following documentation:
# how to chose a database model: https://docs.nautobot.com/projects/core/en/stable/plugins/development/#database-models
# If you want to use the extras_features decorator please reference the following documentation
# https://docs.nautobot.com/projects/core/en/stable/development/core/model-checklist/#extras-features
@extras_features("custom_links", "custom_validators", "export_templates", "graphql", "webhooks")
class NautobotDigitalTwinExampleModel(PrimaryModel):  # pylint: disable=too-many-ancestors
    """Base model for Nautobot Digital Twin app."""

    name = models.CharField(max_length=CHARFIELD_MAX_LENGTH, unique=True)
    description = models.CharField(max_length=CHARFIELD_MAX_LENGTH, blank=True)
    # additional model fields

    class Meta:
        """Meta class."""

        ordering = ["name"]

        # Option for fixing capitalization (i.e. "Snmp" vs "SNMP")
        # verbose_name = "Nautobot Digital Twin"

        # Option for fixing plural name (i.e. "Chicken Tenders" vs "Chicken Tendies")
        # verbose_name_plural = "Nautobot Digital Twins"

    def __str__(self):
        """Stringify instance."""
        return self.name
