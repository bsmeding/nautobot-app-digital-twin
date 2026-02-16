"""Tests for config_filter module."""
from nautobot_digital_twin.config_filter import filter_config_remove_blocks


def test_filter_removes_interface_block():
    """Interface block and its children are removed when pattern matches."""
    config = """hostname foo
!
interface GigabitEthernet0/0
 description Management
 ip address 10.0.0.1 255.255.255.0
 shutdown
!
interface GigabitEthernet0/1
 description Uplink
"""
    result = filter_config_remove_blocks(config, ["GigabitEthernet0/0"])
    assert "interface GigabitEthernet0/0" not in result
    assert "interface GigabitEthernet0/1" in result
    assert "description Uplink" in result


def test_filter_keeps_same_text_under_other_blocks():
    """Text like 'Management' can appear under other interfaces; only remove matched block."""
    config = """interface GigabitEthernet0/0
 description Mgmt-link
 ip address 192.168.1.1 255.255.255.0
!
interface GigabitEthernet0/1
 description Management
 ip address 10.0.0.2 255.255.255.0
"""
    result = filter_config_remove_blocks(config, ["GigabitEthernet0/0"])
    assert "interface GigabitEthernet0/0" not in result
    assert "Mgmt-link" not in result
    assert "192.168.1.1" not in result
    # Gi0/1 block kept, including "Management" and "10.0.0.2"
    assert "interface GigabitEthernet0/1" in result
    assert "description Management" in result
    assert "10.0.0.2" in result


def test_filter_removes_radius_block():
    """radius-server block is removed."""
    config = """hostname foo
radius-server host 1.2.3.4 key secret
!
tacacs-server host 5.6.7.8 key other
"""
    result = filter_config_remove_blocks(config, ["radius-server", "tacacs-server"])
    assert "radius-server" not in result
    assert "tacacs-server" not in result
    assert "hostname foo" in result


def test_filter_empty_patterns_passthrough():
    """Empty patterns list returns config unchanged."""
    config = "hostname foo\ninterface Gi0/0\n"
    assert filter_config_remove_blocks(config, []) == config


def test_filter_empty_config_passthrough():
    """Empty config returns empty."""
    assert filter_config_remove_blocks("", ["foo"]) == ""
    assert filter_config_remove_blocks(None, ["foo"]) is None
