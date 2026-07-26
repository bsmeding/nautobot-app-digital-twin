"""
Build an EVE-NG lab plan (nodes + p2p links) from a Nautobot Location.

The plan is consumed by EveNGBackend to create labs via the EVE-NG REST API.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from django.contrib.contenttypes.models import ContentType
from nautobot.dcim.models import Cable, Device, Interface

from nautobot_digital_twin.plugin_config import get_plugin_config

logger = logging.getLogger(__name__)

# Built-in Nautobot platform key -> EVE-NG node defaults (override via EVE_NG_PLATFORM_MAP).
_DEFAULT_PLATFORM_MAP = {
    "arista_eos": {
        "template": "veos",
        "type": "qemu",
        "icon": "AristaSW.png",
        "ethernet": 8,
        "ram": 2048,
        "cpu": 2,
    },
    "eos": {
        "template": "veos",
        "type": "qemu",
        "icon": "AristaSW.png",
        "ethernet": 8,
        "ram": 2048,
        "cpu": 2,
    },
    "veos": {
        "template": "veos",
        "type": "qemu",
        "icon": "AristaSW.png",
        "ethernet": 8,
        "ram": 2048,
        "cpu": 2,
    },
    "cisco_ios": {
        "template": "vios",
        "type": "qemu",
        "icon": "Router.png",
        "ethernet": 4,
        "ram": 1024,
        "cpu": 1,
    },
    "ios": {
        "template": "vios",
        "type": "qemu",
        "icon": "Router.png",
        "ethernet": 4,
        "ram": 1024,
        "cpu": 1,
    },
    "cisco_nxos": {
        "template": "nxosv9k",
        "type": "qemu",
        "icon": "Nexus.png",
        "ethernet": 8,
        "ram": 8192,
        "cpu": 2,
    },
    "nxos": {
        "template": "nxosv9k",
        "type": "qemu",
        "icon": "Nexus.png",
        "ethernet": 8,
        "ram": 8192,
        "cpu": 2,
    },
}


def sanitize_lab_name(name: str) -> str:
    """Return an EVE-NG-safe lab name derived from a Location name."""
    cleaned = re.sub(r"[^\w\s.-]", "", name or "").strip()
    cleaned = re.sub(r"\s+", "_", cleaned)
    return cleaned[:64] or "nautobot_lab"


def _platform_key(device) -> str:
    platform = getattr(device, "platform", None)
    name = (platform.name if platform else "").lower().strip()
    return name.replace(" ", "_")


def resolve_eve_node_spec(device) -> dict[str, Any]:
    """
    Resolve EVE-NG node creation parameters for a Nautobot device.

    Uses EVE_NG_PLATFORM_MAP when set; falls back to built-in defaults.
    Required keys: template, type. Optional: image, icon, ethernet, ram, cpu, console.
    """
    cfg = get_plugin_config()
    platform_map = cfg.get("EVE_NG_PLATFORM_MAP") or {}
    key = _platform_key(device)
    platform_name = key.replace("_", " ")

    entry = None
    if isinstance(platform_map, dict):
        entry = platform_map.get(key) or platform_map.get(platform_name) or platform_map.get(key.replace("_", "-"))

    if isinstance(entry, str):
        spec = {"template": entry, "type": "qemu"}
    elif isinstance(entry, dict):
        spec = dict(entry)
    else:
        spec = dict(_DEFAULT_PLATFORM_MAP.get(key) or {"template": "vios", "type": "qemu", "icon": "Router.png"})

    if "template" not in spec:
        raise ValueError(f"EVE-NG platform map for '{key}' must include 'template'.")
    spec.setdefault("type", "qemu")
    spec.setdefault("name", device.name)
    spec.setdefault("console", "telnet")
    spec.setdefault("config", "Unconfigured")

    # Optional image from software_version when map does not pin one.
    if not spec.get("image"):
        strict = bool(cfg.get("USE_STRICT_SOFTWARE_VERSION", True))
        sw = getattr(device, "software_version", None)
        version_str = getattr(sw, "version", None) if sw else None
        if strict and version_str and spec.get("template"):
            # Leave image unset so EVE uses template default unless user mapped it.
            pass

    return spec


def _normalize_iface_name(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (name or "").lower())


def _iface_alias_forms(name: str) -> set[str]:
    """Return normalized alias forms for common Cisco/Arista-style interface names."""
    raw = (name or "").strip()
    forms = {_normalize_iface_name(raw)}
    # Ethernet1 / Ethernet1/2 -> eth1 / eth12 (digits only after vendor prefix)
    m = re.match(r"^(?:ethernet|eth|e)([\d/]+)$", raw, re.IGNORECASE)
    if m:
        digits = re.sub(r"\D", "", m.group(1))
        forms.update({f"eth{digits}", f"e{digits}", digits})
    m = re.match(r"^(?:gigabitethernet|gi|g)([\d/]+)$", raw, re.IGNORECASE)
    if m:
        digits = re.sub(r"\D", "", m.group(1))
        forms.update({f"gi{digits}", f"gigabitethernet{digits}", digits})
    m = re.match(r"^(?:tengigabitethernet|tengige|te)([\d/]+)$", raw, re.IGNORECASE)
    if m:
        digits = re.sub(r"\D", "", m.group(1))
        forms.update({f"te{digits}", f"tengigabitethernet{digits}", digits})
    return {f for f in forms if f}


def match_eve_interface(nautobot_iface_name: str, eve_interfaces: list[dict]) -> tuple[int, dict] | None:
    """
    Match a Nautobot interface name to an EVE-NG ethernet interface entry.

    eve_interfaces: list of dicts with at least 'name' (as returned by EVE /interfaces).
    Returns (index, interface_dict) or None.
    """
    if not eve_interfaces:
        return None
    target_forms = _iface_alias_forms(nautobot_iface_name)
    for idx, intf in enumerate(eve_interfaces):
        eve_name = intf.get("name") if isinstance(intf, dict) else str(intf)
        eve_forms = _iface_alias_forms(str(eve_name))
        if target_forms & eve_forms:
            return idx, intf if isinstance(intf, dict) else {"name": eve_name}
    return None


def build_eveng_lab_plan(location, device_filter=None) -> dict[str, Any]:
    """
    Build a serializable lab plan for EVE-NG from Nautobot Location data.

    Returns:
      {
        "lab_name": str,
        "nodes": [{"device_name": str, "spec": dict}, ...],
        "links": [{"name": str, "a_device": str, "a_iface": str, "z_device": str, "z_iface": str}, ...],
      }
    """
    device_qs = Device.objects.filter(location=location).select_related("platform", "software_version")
    if device_filter:
        device_qs = device_qs.filter(**device_filter)
    devices = list(device_qs.order_by("name"))
    if not devices:
        raise ValueError(f"No devices found at location '{location.name}'.")

    nodes = []
    for idx, device in enumerate(devices):
        spec = resolve_eve_node_spec(device)
        # Spread nodes on the canvas for readability.
        spec.setdefault("left", f"{20 + (idx % 5) * 15}%")
        spec.setdefault("top", f"{20 + (idx // 5) * 15}%")
        nodes.append({"device_name": device.name, "spec": spec})

    device_ids = {d.pk for d in devices}
    interface_ct = ContentType.objects.get_for_model(Interface)
    interface_ids = list(Interface.objects.filter(device__id__in=device_ids).values_list("pk", flat=True))

    links = []
    seen = set()
    if interface_ids:
        for cable in Cable.objects.filter(
            termination_a_type=interface_ct,
            termination_a_id__in=interface_ids,
            termination_b_type=interface_ct,
            termination_b_id__in=interface_ids,
        ):
            a = getattr(cable, "termination_a", None)
            b = getattr(cable, "termination_b", None)
            if a is None or b is None or not isinstance(a, Interface) or not isinstance(b, Interface):
                continue
            if a.device_id not in device_ids or b.device_id not in device_ids:
                continue
            key = tuple(sorted([(a.device.name, a.name), (b.device.name, b.name)]))
            if key in seen:
                continue
            seen.add(key)
            links.append(
                {
                    "name": f"link_{a.device.name}_{b.device.name}_{len(links) + 1}",
                    "a_device": a.device.name,
                    "a_iface": a.name,
                    "z_device": b.device.name,
                    "z_iface": b.name,
                }
            )

    lab_name = sanitize_lab_name(location.name)
    logger.info(
        "Built EVE-NG lab plan for %s: %d node(s), %d link(s)",
        location.name,
        len(nodes),
        len(links),
    )
    return {"lab_name": lab_name, "nodes": nodes, "links": links}
