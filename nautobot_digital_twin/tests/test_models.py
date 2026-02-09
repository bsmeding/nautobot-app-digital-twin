"""Test NautobotDigitalTwinExampleModel."""

from nautobot.apps.testing import ModelTestCases

from nautobot_digital_twin import models
from nautobot_digital_twin.tests import fixtures


class TestNautobotDigitalTwinExampleModel(ModelTestCases.BaseModelTestCase):
    """Test NautobotDigitalTwinExampleModel."""

    model = models.NautobotDigitalTwinExampleModel

    @classmethod
    def setUpTestData(cls):
        """Create test data for NautobotDigitalTwinExampleModel Model."""
        super().setUpTestData()
        # Create 3 objects for the model test cases.
        fixtures.create_nautobotdigitaltwinexamplemodel()

    def test_create_nautobotdigitaltwinexamplemodel_only_required(self):
        """Create with only required fields, and validate null description and __str__."""
        nautobotdigitaltwinexamplemodel = models.NautobotDigitalTwinExampleModel.objects.create(name="Development")
        self.assertEqual(nautobotdigitaltwinexamplemodel.name, "Development")
        self.assertEqual(nautobotdigitaltwinexamplemodel.description, "")
        self.assertEqual(str(nautobotdigitaltwinexamplemodel), "Development")

    def test_create_nautobotdigitaltwinexamplemodel_all_fields_success(self):
        """Create NautobotDigitalTwinExampleModel with all fields."""
        nautobotdigitaltwinexamplemodel = models.NautobotDigitalTwinExampleModel.objects.create(name="Development", description="Development Test")
        self.assertEqual(nautobotdigitaltwinexamplemodel.name, "Development")
        self.assertEqual(nautobotdigitaltwinexamplemodel.description, "Development Test")
