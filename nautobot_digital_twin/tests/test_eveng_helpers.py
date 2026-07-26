"""Unit tests for EVE-NG topology helpers (no live EVE-NG required)."""

from django.test import SimpleTestCase

from nautobot_digital_twin.topology.eveng import match_eve_interface, sanitize_lab_name


class EveNGTopologyHelperTest(SimpleTestCase):
    def test_sanitize_lab_name(self):
        self.assertEqual(sanitize_lab_name("Site A"), "Site_A")
        self.assertEqual(sanitize_lab_name("lab/prod!"), "labprod")
        self.assertEqual(sanitize_lab_name(""), "nautobot_lab")

    def test_match_eve_interface_exact(self):
        ifaces = [{"name": "e0/0", "network_id": 0}, {"name": "e0/1", "network_id": 0}]
        match = match_eve_interface("e0/1", ifaces)
        self.assertIsNotNone(match)
        self.assertEqual(match[0], 1)

    def test_match_eve_interface_normalized(self):
        ifaces = [{"name": "Gi0/0"}, {"name": "Gi0/1"}]
        match = match_eve_interface("GigabitEthernet0/1", ifaces)
        self.assertIsNotNone(match)
        self.assertEqual(match[0], 1)
