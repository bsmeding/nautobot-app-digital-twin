"""API views for nautobot_digital_twin."""

from nautobot.apps.api import NautobotModelViewSet

from nautobot_digital_twin import filters, models
from nautobot_digital_twin.api import serializers


class NautobotDigitalTwinExampleModelViewSet(NautobotModelViewSet):  # pylint: disable=too-many-ancestors
    """NautobotDigitalTwinExampleModel viewset."""

    queryset = models.NautobotDigitalTwinExampleModel.objects.all()
    serializer_class = serializers.NautobotDigitalTwinExampleModelSerializer
    filterset_class = filters.NautobotDigitalTwinExampleModelFilterSet

    # Option for modifying the default HTTP methods:
    # http_method_names = ["get", "post", "put", "patch", "delete", "head", "options", "trace"]


class DigitalTwinDeploymentViewSet(NautobotModelViewSet):
    """DigitalTwinDeployment API viewset."""

    queryset = models.DigitalTwinDeployment.objects.all()
    serializer_class = serializers.DigitalTwinDeploymentSerializer
    filterset_class = filters.DigitalTwinDeploymentFilterSet
