"""Unit tests for views."""

from nautobot.apps.testing import ViewTestCases

from nautobot_digital_twin import models
from nautobot_digital_twin.tests import fixtures


class NautobotDigitalTwinExampleModelViewTest(ViewTestCases.PrimaryObjectViewTestCase):
    # pylint: disable=too-many-ancestors
    """Test the NautobotDigitalTwinExampleModel views."""

    model = models.NautobotDigitalTwinExampleModel
    bulk_edit_data = {"description": "Bulk edit views"}
    form_data = {
        "name": "Test 1",
        "description": "Initial model",
    }

    update_data = {
        "name": "Test 2",
        "description": "Updated model",
    }

    @classmethod
    def setUpTestData(cls):
        fixtures.create_nautobotdigitaltwinexamplemodel()
