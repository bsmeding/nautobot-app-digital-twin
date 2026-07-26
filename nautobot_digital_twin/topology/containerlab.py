"""
Generate containerlab topology YAML from a Nautobot Location (devices + cables).
Used when backend is containerlab: build YAML from site data, then upload to containerlab server.
"""

import ipaddress
import logging
import re

from nautobot.dcim.models import Device

from nautobot_digital_twin.plugin_config import get_plugin_config
from nautobot_digital_twin.topology.cables import iter_interface_cable_pairs

logger = logging.getLogger(__name__)


def _get_primary_ip_cidr(device):
    """Return (subnet_cidr, host_ip) from device.primary_ip4, or (None, None)."""
    primary = getattr(device, "primary_ip4", None)
    if not primary:
        return None, None
    addr_str = getattr(primary, "address", None)
    if addr_str is not None:
        addr_str = str(addr_str)
    if not addr_str:
        addr_str = getattr(primary, "cidr", None)
    if not addr_str and hasattr(primary, "host") and hasattr(primary, "mask_length"):
        addr_str = f"{primary.host}/{primary.mask_length}"
    if not addr_str:
        addr_str = str(primary)
    try:
        if "/" not in str(addr_str):
            addr_str = f"{addr_str}/32"
        iface = ipaddress.ip_interface(addr_str)
        return str(iface.network), str(iface.ip)
    except (ValueError, ipaddress.AddressValueError) as e:
        logger.warning("Invalid primary_ip4 for %s: %s", device.name, e)
        return None, None


def _get_mgmt_from_devices(devices):
    """
    Extract mgmt subnet and per-device IPs from primary_ip4.
    Returns (mgmt_subnet, device_mgmt_ips) or (None, {}).
    """
    device_mgmt_ips = {}
    subnets = set()
    for dev in devices:
        subnet_cidr, host_ip = _get_primary_ip_cidr(dev)
        if subnet_cidr and host_ip:
            device_mgmt_ips[dev.name] = (subnet_cidr, host_ip)
            subnets.add(subnet_cidr)
    if not device_mgmt_ips:
        return None, {}
    mgmt_subnet = subnets.pop() if len(subnets) == 1 else (subnets.pop() if subnets else None)
    if subnets:
        logger.warning("Devices have different mgmt subnets; using %s", mgmt_subnet)
    try:
        mgmt_network = ipaddress.ip_network(mgmt_subnet)
    except ValueError:
        return None, {}
    result = {}
    for dev_name, (subnet_cidr, host_ip) in device_mgmt_ips.items():
        try:
            if ipaddress.ip_address(host_ip) in mgmt_network:
                result[dev_name] = host_ip
        except ValueError:
            pass
    return mgmt_subnet, result


# Containerlab image name -> kind (for simple platform->image mapping)
_CLAB_IMAGE_TO_KIND = {
    "ceos": "arista_ceos",
    "ios": "cisco_ios",
    "iol": "cisco_ios",
}


def _nautobot_iface_to_clab(nautobot_name: str) -> str:
    """
    Map a Nautobot interface name to its containerlab equivalent.

    Examples:
      Ethernet1            -> eth1
      Ethernet1/2          -> eth1-2
      Management0          -> mgmt0
      Loopback0            -> lo0
      Port-channel1        -> po1
      GigabitEthernet0/1   -> ge-0-1
      FastEthernet0/1      -> fe-0-1
      TenGigabitEthernet1  -> te-1
      HundredGigE1         -> hu-1
    """
    # Ethernet1 or Ethernet1/2/3
    m = re.match(r"^Ethernet(\d+(?:[/]\d+)*)$", nautobot_name, re.IGNORECASE)
    if m:
        return "eth" + m.group(1).replace("/", "-")

    # Management0, Management1
    m = re.match(r"^Management(\d*)$", nautobot_name, re.IGNORECASE)
    if m:
        return f"mgmt{m.group(1)}"

    # Loopback0
    m = re.match(r"^Loopback(\d+)$", nautobot_name, re.IGNORECASE)
    if m:
        return f"lo{m.group(1)}"

    # Port-channel1 or PortChannel1
    m = re.match(r"^Port-?[Cc]hannel(\d+)$", nautobot_name, re.IGNORECASE)
    if m:
        return f"po{m.group(1)}"

    # GigabitEthernet0/1
    m = re.match(r"^GigabitEthernet(\d+(?:[/]\d+)*)$", nautobot_name, re.IGNORECASE)
    if m:
        return "ge-" + m.group(1).replace("/", "-")

    # FastEthernet0/1
    m = re.match(r"^FastEthernet(\d+(?:[/]\d+)*)$", nautobot_name, re.IGNORECASE)
    if m:
        return "fe-" + m.group(1).replace("/", "-")

    # TenGigabitEthernet / TenGigE
    m = re.match(r"^(?:TenGigabitEthernet|TenGigE)(\d+(?:[/]\d+)*)$", nautobot_name, re.IGNORECASE)
    if m:
        return "te-" + m.group(1).replace("/", "-")

    # HundredGigE / HundredGigabitEthernet
    m = re.match(r"^(?:HundredGigE|HundredGigabitEthernet)(\d+(?:[/]\d+)*)$", nautobot_name, re.IGNORECASE)
    if m:
        return "hu-" + m.group(1).replace("/", "-")

    # Fallback: lowercase, strip non-alphanumeric except hyphen
    sanitized = re.sub(r"[^a-z0-9-]", "", nautobot_name.lower())
    return sanitized or "eth0"


def _platform_to_clab_kind_image(device):
    """
    Return (kind, image, extra) for containerlab node from Nautobot device platform/software_version.
    extra: dict of additional node fields (e.g. {"cmd": "..."} from platform map entry).
    Uses CONTAINERLAB_PLATFORM_MAP if set; falls back to built-in mappings.
    """
    platform = getattr(device, "platform", None)
    sw_version = getattr(device, "software_version", None)
    platform_name = (platform.name if platform else "").lower()
    platform_key = platform_name.replace(" ", "_")
    cfg = get_plugin_config()
    platform_map = cfg.get("CONTAINERLAB_PLATFORM_MAP") or {}
    strict_version = bool(cfg.get("USE_STRICT_SOFTWARE_VERSION", True))
    extra = {}
    if isinstance(platform_map, dict):
        entry = platform_map.get(platform_name) or platform_map.get(platform_key)
        if entry is not None:
            if isinstance(entry, str):
                kind = _CLAB_IMAGE_TO_KIND.get(entry, platform_key or "linux")
                return kind, entry, extra
            if isinstance(entry, dict):
                kind = entry.get("kind")
                image = entry.get("image")
                if kind and image:
                    if "cmd" in entry:
                        extra["cmd"] = entry["cmd"]
                    return kind, image, extra
    # Built-in: Arista EOS / cEOS / vEOS -> ceos
    if platform_name in ("eos", "ceos", "veos"):
        if strict_version:
            version_str = getattr(sw_version, "version", None)
            if not version_str:
                version_str = "4.34.2F"
            image = f"ceos:{version_str}"
        else:
            image = "ceos"
        return "arista_ceos", image, extra
    # Default
    return "linux", "alpine:latest", extra


def build_containerlab_yaml(location, device_startup_configs=None, device_filter=None):
    """
    Build a containerlab topology YAML string for the given Location.

    device_startup_configs: optional dict mapping device name -> relative config filename.
    device_filter: optional dict of queryset filter kwargs applied to Device.objects.filter()
                   (e.g. {"role__name": "Leaf", "tags__name": "lab-ready"}) to deploy a subset.
    When USE_PRIMARY_IP_FOR_MGMT is True (default), primary_ip4 addresses are used to set
    per-node mgmt-ipv4 and a shared mgmt subnet in the topology.
    """
    qs = Device.objects.filter(location=location)
    if device_filter:
        qs = qs.filter(**device_filter)
    devices = list(qs.order_by("name"))
    if not devices:
        logger.warning(
            "No devices at location %s (filter: %s); generating empty topology", location.name, device_filter
        )
        return _empty_topology_yaml(location)

    name = re.sub(r"[^a-z0-9-]", "-", location.name.lower()).strip("-") or "lab"

    cfg = get_plugin_config()
    use_primary_ip = bool(cfg.get("USE_PRIMARY_IP_FOR_MGMT", True))
    mgmt_subnet = None
    device_mgmt_ips = {}
    if use_primary_ip:
        mgmt_subnet, device_mgmt_ips = _get_mgmt_from_devices(devices)

    nodes = {}
    for dev in devices:
        kind, image, extra = _platform_to_clab_kind_image(dev)
        node_cfg = {"kind": kind, "image": image}
        node_cfg.update(extra)
        if kind == "linux" and "cmd" not in node_cfg:
            node_cfg["cmd"] = "sleep infinity"
        if device_startup_configs and dev.name in device_startup_configs:
            node_cfg["startup-config"] = device_startup_configs[dev.name]
            node_cfg["enforce-startup-config"] = True
        if device_mgmt_ips and dev.name in device_mgmt_ips:
            node_cfg["mgmt-ipv4"] = device_mgmt_ips[dev.name]
        nodes[dev.name] = node_cfg

    device_ids = {dev.id for dev in devices}
    links = []
    seen = set()
    for a, b in iter_interface_cable_pairs(device_ids):
        endpoint_a = f"{a.device.name}:{_nautobot_iface_to_clab(a.name)}"
        endpoint_b = f"{b.device.name}:{_nautobot_iface_to_clab(b.name)}"
        key = tuple(sorted([endpoint_a, endpoint_b]))
        if key in seen:
            continue
        seen.add(key)
        links.append({"endpoints": [endpoint_a, endpoint_b]})

    return _render_yaml(name, nodes, links, mgmt_subnet=mgmt_subnet)


def get_required_images_for_location(location, device_filter=None):
    """
    Return the set of container image names needed to deploy the topology for this location.
    Accepts the same device_filter as build_containerlab_yaml.
    """
    qs = Device.objects.filter(location=location)
    if device_filter:
        qs = qs.filter(**device_filter)
    images = set()
    for dev in qs:
        _, image, _ = _platform_to_clab_kind_image(dev)
        images.add(image)
    return images


def build_mermaid_topology(location):
    """
    Build a Mermaid graph description for the given Location.
    Edges include interface labels (e.g. "Ethernet1:Ethernet1") so the diagram is informative.

    Example output:

        graph LR
          "spine1" ---|"Ethernet1:Ethernet1"| "leaf1"
          "leaf1" ---|"Ethernet2:Ethernet1"| "host1"
    """
    devices = list(Device.objects.filter(location=location).order_by("name"))
    if not devices:
        return "graph LR\n  %% No devices at this location\n"

    device_names = {dev.id: dev.name for dev in devices}
    device_ids = set(device_names)
    edges = {}
    for a, b in iter_interface_cable_pairs(device_ids):
        name_a = device_names.get(a.device_id)
        name_b = device_names.get(b.device_id)
        if not name_a or not name_b or name_a == name_b:
            continue
        key = tuple(sorted((name_a, name_b)))
        if key not in edges:
            if name_a <= name_b:
                edges[key] = (name_a, name_b, a.name, b.name)
            else:
                edges[key] = (name_b, name_a, b.name, a.name)

    lines = ["graph LR"]
    if not edges:
        for name in sorted(device_names.values()):
            # Quote node names to handle hyphens and special characters
            lines.append(f'  "{name}"')
    else:
        for key in sorted(edges):
            dev_a, dev_b, if_a, if_b = edges[key]
            # Use ":" as separator — avoid "--" which Mermaid parses as an edge marker
            label = f"{if_a}:{if_b}"
            lines.append(f'  "{dev_a}" ---|"{label}"| "{dev_b}"')
    return "\n".join(lines)


def _empty_topology_yaml(location):
    name = re.sub(r"[^a-z0-9-]", "-", location.name.lower()).strip("-") or "lab"
    return _render_yaml(name, {}, [])


def _render_yaml(name, nodes, links, mgmt_subnet=None):
    """Render containerlab topology dict to YAML string."""
    import yaml

    data = {
        "name": name,
        "topology": {
            "nodes": nodes or {"placeholder": {"kind": "linux", "image": "alpine:latest", "cmd": "sleep infinity"}},
            "links": links,
        },
    }
    if mgmt_subnet:
        data["mgmt"] = {"ipv4-subnet": mgmt_subnet}
    return yaml.dump(data, default_flow_style=False, sort_keys=False, allow_unicode=True)
