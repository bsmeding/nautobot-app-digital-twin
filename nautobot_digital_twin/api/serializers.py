"""API serializers for nautobot_digital_twin."""

from nautobot.apps.api import NautobotModelSerializer, TaggedModelSerializerMixin

from nautobot_digital_twin import models


class NautobotDigitalTwinExampleModelSerializer(NautobotModelSerializer, TaggedModelSerializerMixin):  # pylint: disable=too-many-ancestors
    """NautobotDigitalTwinExampleModel Serializer."""

    class Meta:
        """Meta attributes."""

        model = models.NautobotDigitalTwinExampleModel
        fields = "__all__"

        # Option for disabling write for certain fields:
        # read_only_fields = []


class DigitalTwinDeploymentSerializer(NautobotModelSerializer, TaggedModelSerializerMixin):
    """DigitalTwinDeployment serializer."""

    class Meta:
        model = models.DigitalTwinDeployment
        fields = "__all__"
