"""Tests for config_filter module."""
from nautobot_digital_twin.config_filter import (
    filter_config_remove_blocks,
    filter_config_replace,
    filter_config_append_add_lines,
    build_minimal_config_from_add_lines,
)


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


def test_filter_config_replace():
    """Replace patterns are applied."""
    config = "aaa authentication login default group radius\nline vty 0 4\n login\n"
    patterns = [("group radius", "local"), ("group tacacs+", "local")]
    result = filter_config_replace(config, patterns)
    assert "group radius" not in result
    assert "local" in result
    assert "aaa authentication login default local" in result


def test_filter_config_replace_empty_passthrough():
    """Empty patterns returns config unchanged."""
    config = "hostname foo"
    assert filter_config_replace(config, []) == config
    assert filter_config_replace("", [("a", "b")]) == ""


def test_filter_config_append_add_lines():
    """Platform add config lines are appended when platform is in map."""
    config = "hostname leaf1\n!"
    platform_add = {
        "arista_eos": [
            "username {username} privilege 15 role network-admin secret {password}",
        ],
    }
    result = filter_config_append_add_lines(config, "arista_eos", "admin", "secret123", platform_add)
    assert "username admin privilege 15 role network-admin secret secret123" in result
    assert "hostname leaf1" in result


def test_filter_config_append_add_lines_before_end():
    """Add config lines are inserted before 'end' line (Arista, Cisco)."""
    config = "hostname leaf1\n!\nmanagement api http-commands\n   no shutdown\n!\nend"
    platform_add = {
        "arista_eos": ["username {username} privilege 15 role network-admin secret {password}"],
    }
    result = filter_config_append_add_lines(config, "arista_eos", "admin", "admin", platform_add)
    # Username block must appear before "end"
    end_pos = result.find("end")
    username_pos = result.find("username admin")
    assert username_pos < end_pos
    assert result.endswith("end") or "end" in result


def test_filter_config_append_add_lines_platform_not_configured():
    """No append when platform not in map."""
    config = "hostname leaf1"
    platform_add = {"cisco_ios": ["username {username} secret {password}"]}
    result = filter_config_append_add_lines(config, "arista_eos", "admin", "x", platform_add)
    assert result == config


def test_filter_config_append_add_lines_empty_map():
    """No append when platform_add_config_lines is empty."""
    config = "hostname leaf1"
    result = filter_config_append_add_lines(config, "arista_eos", "admin", "x", {})
    assert result == config


def test_build_minimal_config_from_add_lines():
    """Minimal config is built from platform add config lines."""
    platform_add = {"arista_eos": ["username {username} privilege 15 role network-admin secret {password}"]}
    result = build_minimal_config_from_add_lines("arista_eos", "admin", "secret123", platform_add)
    assert "username admin privilege 15 role network-admin secret secret123" in result
    assert result.startswith("!")


def test_build_minimal_config_platform_not_configured():
    """Empty when platform not in map."""
    platform_add = {"cisco_ios": ["username {username} secret {password}"]}
    assert build_minimal_config_from_add_lines("arista_eos", "admin", "x", platform_add) == ""
