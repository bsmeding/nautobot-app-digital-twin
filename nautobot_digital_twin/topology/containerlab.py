"""
Generate containerlab topology YAML from a Nautobot Location (devices + cables).
Used when backend is containerlab: build YAML from site data, then upload to containerlab server.
"""
import ipaddress
import re
import logging

from django.contrib.contenttypes.models import ContentType
from nautobot.dcim.models import Cable, Device, Interface

from nautobot_digital_twin.plugin_config import get_plugin_config

logger = logging.getLogger(__name__)


def _get_primary_ip_cidr(device):
    """Return (subnet_cidr, host_ip) from device.primary_ip4, or (None, None)."""
    primary = getattr(device, "primary_ip4", None)
    if not primary:
        return None, None
    # IPAddress: address (CIDR), host+mask_length, or address as IPNetwork
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

    Returns (mgmt_subnet, device_mgmt_ips) or (None, {}) if not enough data.
    mgmt_subnet: e.g. "10.0.0.0/24"
    device_mgmt_ips: {device_name: "10.0.0.1"} - only devices whose IP is in mgmt_subnet
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
    # Use first subnet if all same; if mixed, use the most common or first
    mgmt_subnet = subnets.pop() if len(subnets) == 1 else (subnets.pop() if subnets else None)
    if subnets:
        logger.warning("Devices have different mgmt subnets; using %s", mgmt_subnet)
    # Only include device IPs that fall within the chosen mgmt_subnet
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

# Map Nautobot interface name to containerlab interface name (e.g. Ethernet1 -> eth1)
def _nautobot_iface_to_clab(nautobot_name: str) -> str:
    """Ethernet1 -> eth1, GigabitEthernet0/0/1 -> eth1 (for Linux nodes), etc."""
    match = re.match(r"^Ethernet(\d+)$", nautobot_name, re.IGNORECASE)
    if match:
        return f"eth{match.group(1)}"
    # Cisco-style: GigabitEthernet0/0/1, Gi0/0/1 -> eth1 (containerlab Linux uses eth1, eth2, ...)
    match = re.match(r"^(?:GigabitEthernet|Gi|FastEthernet|Fa)0/0/(\d+)$", nautobot_name, re.IGNORECASE)
    if match:
        return f"eth{match.group(1)}"
    # Fallback: lowercase, strip spaces
    return nautobot_name.lower().replace(" ", "").replace("-", "") or "eth1"


def _platform_to_clab_kind_image(device):
    """Return (kind, image, extra) for containerlab node from Nautobot device platform/software_version.
    Uses CONTAINERLAB_PLATFORM_MAP if set: platform name (lowercase) -> image string or dict.
    e.g. {"arista_eos": "ceos", "cisco_ios": "ios"} or {"cisco_ios": "iol"}.
    Dict format can include "cmd" for custom startup (e.g. Linux client with IP setup).
    Kind is derived from platform name (spaces -> underscores). When empty, built-in (eos/ceos/veos -> ceos).
    """
    platform = getattr(device, "platform", None)
    sw_version = getattr(device, "software_version", None)
    platform_name = (platform.name if platform else "").lower()
    platform_key = platform_name.replace(" ", "_")  # "Arista EOS" -> "arista_eos"
    cfg = get_plugin_config()
    platform_map = cfg.get("CONTAINERLAB_PLATFORM_MAP") or {}
    strict_version = bool(cfg.get("USE_STRICT_SOFTWARE_VERSION", True))
    extra = {}
    if isinstance(platform_map, dict):
        entry = platform_map.get(platform_name) or platform_map.get(platform_key)
        if entry is not None:
            if isinstance(entry, str):
                # Simple format: platform -> image (e.g. arista_eos: ceos, cisco_ios: ios)
                kind = _CLAB_IMAGE_TO_KIND.get(entry, platform_key or "linux")
                return kind, entry, extra
            if isinstance(entry, dict):
                kind = entry.get("kind")
                image = entry.get("image")
                if kind and image:
                    if "cmd" in entry:
                        extra["cmd"] = entry["cmd"]
                    return kind, image, extra
    # Built-in: Arista EOS / cEOS / vEOS -> containerlab ceos
    if platform_name in ("eos", "ceos", "veos"):
        if strict_version:
            version_str = getattr(sw_version, "version", None)
            if not version_str:
                # No explicit software_version on the device; fall back to a safe default
                version_str = "4.34.2F"
            image = f"ceos:{version_str}"
        else:
            # Non-strict: omit tag so container runtime uses default/latest ceos image
            image = "ceos"
        return "arista_ceos", image, extra
    # Default for unknown platform
    return "linux", "alpine:latest", extra


def build_containerlab_yaml(location, device_startup_configs=None):
    """
    Build a containerlab topology YAML string for the given Location.

    Uses Devices at this location, their interfaces, and Cables between them to produce
    a topology with nodes (kind/image from platform and software_version) and links.

    device_startup_configs: optional dict mapping device name to relative config filename
    (e.g. {"leaf1": "leaf1.cfg"}). When set, each node gets startup-config pointing to that
    file (path relative to the topology file, so configs must be in the same directory).
    """
    devices = list(Device.objects.filter(location=location).order_by("name"))
    if not devices:
        logger.warning("No devices at location %s; generating empty topology", location.name)
        return _empty_topology_yaml(location)

    # Lab name: sanitize for containerlab (lowercase, no spaces)
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
        node_name = dev.name  # containerlab will use this as hostname
        node_cfg = {"kind": kind, "image": image}
        node_cfg.update(extra)
        # Linux/alpine containers exit immediately without a foreground process; keep them running
        if kind == "linux" and "cmd" not in node_cfg:
            node_cfg["cmd"] = "sleep infinity"
        if device_startup_configs and dev.name in device_startup_configs:
            # Path relative to topology file (same directory on containerlab server).
            # enforce-startup-config ensures our file is used even if lab dir has old config.
            node_cfg["startup-config"] = device_startup_configs[dev.name]
            node_cfg["enforce-startup-config"] = True
        if device_mgmt_ips and dev.name in device_mgmt_ips:
            node_cfg["mgmt-ipv4"] = device_mgmt_ips[dev.name]
        nodes[node_name] = node_cfg

    # Build links from Cable: only cables between interfaces at this location (avoids loading all cables)
    interface_ct = ContentType.objects.get_for_model(Interface)
    interface_ids = list(
        Interface.objects.filter(device__location=location).values_list("pk", flat=True)
    )
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
            dev_a, if_a = a.device, a.name
            dev_b, if_b = b.device, b.name
            endpoint_a = f"{dev_a.name}:{_nautobot_iface_to_clab(if_a)}"
            endpoint_b = f"{dev_b.name}:{_nautobot_iface_to_clab(if_b)}"
            key = tuple(sorted([endpoint_a, endpoint_b]))
            if key in seen:
                continue
            seen.add(key)
            links.append({"endpoints": [endpoint_a, endpoint_b]})

    return _render_yaml(name, nodes, links, mgmt_subnet=mgmt_subnet)


def get_required_images_for_location(location):
    """
    Return the set of container image names (e.g. {"ceos:4.34.2F", "alpine:latest"})
    needed to deploy the topology for this location. Uses the same platform mapping as
    build_containerlab_yaml, so this can be used to verify images exist before deploy.
    """
    devices = list(Device.objects.filter(location=location))
    images = set()
    for dev in devices:
        _, image, _ = _platform_to_clab_kind_image(dev)
        images.add(image)
    return images


def build_mermaid_topology(location):
    """
    Build a simple Mermaid graph description for the given Location.

    This mirrors the topology we generate for containerlab, but only connects
    devices by name (without per-interface detail) so it can be rendered easily
    in Nautobot or any Mermaid viewer.

    Example output:

        graph LR
          spine1 --- leaf1
          leaf1 --- host1
    """
    devices = list(Device.objects.filter(location=location).order_by("name"))
    if not devices:
        return "graph LR\n  %% No devices at this location\n"

    # Map device IDs to names for quick lookup
    device_names = {dev.id: dev.name for dev in devices}

    # Build links from cables between interfaces at this location
    interface_ct = ContentType.objects.get_for_model(Interface)
    interface_ids = list(
        Interface.objects.filter(device__location=location).values_list("pk", flat=True)
    )
    edges = set()
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
            dev_a = a.device
            dev_b = b.device
            name_a = device_names.get(dev_a.id)
            name_b = device_names.get(dev_b.id)
            if not name_a or not name_b or name_a == name_b:
                continue
            edge = tuple(sorted((name_a, name_b)))
            edges.add(edge)

    lines = ["graph LR"]
    if not edges:
        # No cables, just list devices
        for name in device_names.values():
            lines.append(f"  {name}")
    else:
        for a, b in sorted(edges):
            lines.append(f"  {a} --- {b}")
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
