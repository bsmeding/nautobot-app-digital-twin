"""Filtering for nautobot_digital_twin."""

from nautobot.apps.filters import NameSearchFilterSet, NautobotFilterSet

from nautobot_digital_twin import models


class NautobotDigitalTwinExampleModelFilterSet(NameSearchFilterSet, NautobotFilterSet):  # pylint: disable=too-many-ancestors
    """Filter for NautobotDigitalTwinExampleModel."""

    class Meta:
        """Meta attributes for filter."""

        model = models.NautobotDigitalTwinExampleModel

        # add any fields from the model that you would like to filter your searches by using those
        fields = "__all__"


class DigitalTwinDeploymentFilterSet(NautobotFilterSet):
    """Filter for DigitalTwinDeployment."""

    class Meta:
        model = models.DigitalTwinDeployment
        fields = "__all__"
