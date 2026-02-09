"""Views for nautobot_digital_twin."""

from nautobot.apps.views import NautobotUIViewSet
from nautobot.apps.ui import ObjectDetailContent, ObjectFieldsPanel, SectionChoices

from nautobot_digital_twin import filters, forms, models, tables
from nautobot_digital_twin.api import serializers


class DigitalTwinDeploymentUIViewSet(NautobotUIViewSet):
    """ViewSet for Digital Twin Deployment list and detail (created by Start/Stop jobs)."""

    filterset_class = filters.DigitalTwinDeploymentFilterSet
    filterset_form_class = forms.DigitalTwinDeploymentFilterForm
    form_class = forms.DigitalTwinDeploymentForm
    queryset = models.DigitalTwinDeployment.objects.all()
    serializer_class = serializers.DigitalTwinDeploymentSerializer
    table_class = tables.DigitalTwinDeploymentTable
    object_detail_content = ObjectDetailContent(
        panels=[
            ObjectFieldsPanel(
                weight=100,
                section=SectionChoices.LEFT_HALF,
                fields="__all__",
            ),
        ],
    )
