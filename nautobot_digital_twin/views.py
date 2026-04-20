"""Views for nautobot_digital_twin."""

from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404
from django.views import View

from nautobot.apps.views import NautobotUIViewSet

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
    # Detail view uses custom template:
    # templates/nautobot_digital_twin/digitaltwindeployment_retrieve.html


class DigitalTwinTopologyExportView(View):
    """
    Return the containerlab YAML topology for the Location of a given deployment as a file download.
    Generates the YAML fresh from current Nautobot DCIM data (same as deploy would produce).
    URL: /plugins/nautobot-digital-twin/digital-twin-deployments/<pk>/topology.yaml
    """

    def get(self, request, pk):
        from nautobot_digital_twin.topology import build_containerlab_yaml

        deployment = get_object_or_404(models.DigitalTwinDeployment, pk=pk)
        try:
            yaml_content = build_containerlab_yaml(deployment.location)
        except Exception as e:
            raise Http404(f"Could not generate topology: {e}") from e

        filename = f"{deployment.location.name}.clab.yaml"
        response = HttpResponse(yaml_content, content_type="application/x-yaml")
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response
