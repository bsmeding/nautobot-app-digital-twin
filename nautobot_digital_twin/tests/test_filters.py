"""Test NautobotDigitalTwinExampleModel Filter."""

from nautobot.apps.testing import FilterTestCases

from nautobot_digital_twin import filters, models
from nautobot_digital_twin.tests import fixtures


class NautobotDigitalTwinExampleModelFilterTestCase(FilterTestCases.FilterTestCase):
    """NautobotDigitalTwinExampleModel Filter Test Case."""

    queryset = models.NautobotDigitalTwinExampleModel.objects.all()
    filterset = filters.NautobotDigitalTwinExampleModelFilterSet
    generic_filter_tests = (
        ("id",),
        ("created",),
        ("last_updated",),
        ("name",),
    )

    @classmethod
    def setUpTestData(cls):
        """Setup test data for NautobotDigitalTwinExampleModel Model."""
        fixtures.create_nautobotdigitaltwinexamplemodel()

    def test_q_search_name(self):
        """Test using Q search with name of NautobotDigitalTwinExampleModel."""
        params = {"q": "Test One"}
        self.assertEqual(self.filterset(params, self.queryset).qs.count(), 1)

    def test_q_invalid(self):
        """Test using invalid Q search for NautobotDigitalTwinExampleModel."""
        params = {"q": "test-five"}
        self.assertEqual(self.filterset(params, self.queryset).qs.count(), 0)
