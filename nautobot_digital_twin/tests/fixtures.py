"""Create fixtures for tests."""

from nautobot_digital_twin.models import NautobotDigitalTwinExampleModel


def create_nautobotdigitaltwinexamplemodel():
    """Fixture to create necessary number of NautobotDigitalTwinExampleModel for tests."""
    NautobotDigitalTwinExampleModel.objects.create(name="Test One")
    NautobotDigitalTwinExampleModel.objects.create(name="Test Two")
    NautobotDigitalTwinExampleModel.objects.create(name="Test Three")
