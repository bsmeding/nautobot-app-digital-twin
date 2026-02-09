"""Test nautobotdigitaltwinexamplemodel forms."""

from django.test import TestCase

from nautobot_digital_twin import forms


class NautobotDigitalTwinExampleModelTest(TestCase):
    """Test NautobotDigitalTwinExampleModel forms."""

    def test_specifying_all_fields_success(self):
        form = forms.NautobotDigitalTwinExampleModelForm(
            data={
                "name": "Development",
                "description": "Development Testing",
            }
        )
        self.assertTrue(form.is_valid())
        self.assertTrue(form.save())

    def test_specifying_only_required_success(self):
        form = forms.NautobotDigitalTwinExampleModelForm(
            data={
                "name": "Development",
            }
        )
        self.assertTrue(form.is_valid())
        self.assertTrue(form.save())

    def test_validate_name_nautobotdigitaltwinexamplemodel_is_required(self):
        form = forms.NautobotDigitalTwinExampleModelForm(data={"description": "Development Testing"})
        self.assertFalse(form.is_valid())
        self.assertIn("This field is required.", form.errors["name"])
