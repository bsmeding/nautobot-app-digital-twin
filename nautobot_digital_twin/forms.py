"""Forms for nautobot_digital_twin."""

from django import forms
from nautobot.apps.constants import CHARFIELD_MAX_LENGTH
from nautobot.apps.forms import NautobotBulkEditForm, NautobotFilterForm, NautobotModelForm, TagsBulkEditFormMixin

from nautobot_digital_twin import models


class NautobotDigitalTwinExampleModelForm(NautobotModelForm):  # pylint: disable=too-many-ancestors
    """NautobotDigitalTwinExampleModel creation/edit form."""

    class Meta:
        """Meta attributes."""

        model = models.NautobotDigitalTwinExampleModel
        fields = "__all__"


class NautobotDigitalTwinExampleModelBulkEditForm(TagsBulkEditFormMixin, NautobotBulkEditForm):  # pylint: disable=too-many-ancestors
    """NautobotDigitalTwinExampleModel bulk edit form."""

    pk = forms.ModelMultipleChoiceField(queryset=models.NautobotDigitalTwinExampleModel.objects.all(), widget=forms.MultipleHiddenInput)
    description = forms.CharField(required=False, max_length=CHARFIELD_MAX_LENGTH)

    class Meta:
        """Meta attributes."""

        nullable_fields = [
            "description",
        ]


class NautobotDigitalTwinExampleModelFilterForm(NautobotFilterForm):
    """Filter form to filter searches."""

    model = models.NautobotDigitalTwinExampleModel
    field_order = ["q", "name"]

    q = forms.CharField(
        required=False,
        label="Search",
        help_text="Search within Name.",
    )
    name = forms.CharField(required=False, label="Name")


class DigitalTwinDeploymentForm(NautobotModelForm):
    """
    Edit form for DigitalTwinDeployment.
    Exposes only auto_destroy_at for editing — all other fields are set by the Start/Stop jobs.
    """

    class Meta:
        model = models.DigitalTwinDeployment
        fields = ["auto_destroy_at"]
        widgets = {
            "auto_destroy_at": forms.DateTimeInput(
                attrs={"type": "datetime-local"},
                format="%Y-%m-%dT%H:%M",
            ),
        }
        help_texts = {
            "auto_destroy_at": (
                "Date and time when this deployment will be automatically destroyed. "
                "Clear to disable auto-destroy for this deployment."
            ),
        }


class DigitalTwinDeploymentFilterForm(NautobotFilterForm):
    """Filter form for Digital Twin Deployments."""

    model = models.DigitalTwinDeployment
    field_order = ["q", "name", "location", "status", "backend"]
