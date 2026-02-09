"""Tables for nautobot_digital_twin."""

import django_tables2 as tables
from nautobot.apps.tables import BaseTable, ButtonsColumn, ToggleColumn

from nautobot_digital_twin import models


class NautobotDigitalTwinExampleModelTable(BaseTable):
    # pylint: disable=R0903
    """Table for list view."""

    pk = ToggleColumn()
    name = tables.Column(linkify=True)
    actions = ButtonsColumn(
        models.NautobotDigitalTwinExampleModel,
        # Option for modifying the default action buttons on each row:
        # buttons=("changelog", "edit", "delete"),
        # Option for modifying the pk for the action buttons:
        pk_field="pk",
    )

    class Meta(BaseTable.Meta):
        """Meta attributes."""

        model = models.NautobotDigitalTwinExampleModel
        fields = (
            "pk",
            "name",
            "description",
        )

        # Option for modifying the columns that show up in the list view by default:
        # default_columns = (
        #     "pk",
        #     "name",
        #     "description",
        # )


class DigitalTwinDeploymentTable(BaseTable):
    """Table for Digital Twin Deployment list view."""

    pk = ToggleColumn()
    name = tables.Column(linkify=True)
    location = tables.Column(linkify=True)
    status = tables.Column()
    backend = tables.Column()
    deployed_at = tables.DateTimeColumn()
    auto_destroy_at = tables.DateTimeColumn()
    destroyed_at = tables.DateTimeColumn()
    deployed_by = tables.Column()  # User model may not have UI detail URL; show as text only
    actions = ButtonsColumn(
        models.DigitalTwinDeployment,
        pk_field="pk",
    )

    class Meta(BaseTable.Meta):
        model = models.DigitalTwinDeployment
        fields = (
            "pk",
            "name",
            "location",
            "status",
            "backend",
            "deployed_at",
            "auto_destroy_at",
            "destroyed_at",
            "deployed_by",
        )
