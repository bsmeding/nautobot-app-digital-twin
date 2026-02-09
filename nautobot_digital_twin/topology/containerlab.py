"""
Generate containerlab topology YAML from a Nautobot Location (devices + cables).
Used when backend is containerlab: build YAML from site data, then upload to containerlab server.
"""
import re
import logging

from django.contrib.contenttypes.models import ContentType
from nautobot.dcim.models import Cable, Device, Interface

from nautobot_digital_twin.plugin_config import get_plugin_config

logger = logging.getLogger(__name__)

# Map Nautobot interface name to containerlab interface name (e.g. Ethernet1 -> eth1)
def _nautobot_iface_to_clab(nautobot_name: str) -> str:
    """Ethernet1 -> eth1, Ethernet2 -> eth2, etc."""
    match = re.match(r"^Ethernet(\d+)$", nautobot_name, re.IGNORECASE)
    if match:
        return f"eth{match.group(1)}"
    # Fallback: lowercase, strip spaces
    return nautobot_name.lower().replace(" ", "").replace("-", "") or "eth1"


def _platform_to_clab_kind_image(device):
    """Return (kind, image) for containerlab node from Nautobot device platform/software_version.
    Uses CONTAINERLAB_PLATFORM_MAP if set (nautobot platform name -> {kind, image}), else built-in (eos/ceos/veos -> ceos).
    """
    platform = getattr(device, "platform", None)
    sw_version = getattr(device, "software_version", None)
    platform_name = (platform.name if platform else "").lower()
    cfg = get_plugin_config()
    platform_map = cfg.get("CONTAINERLAB_PLATFORM_MAP") or {}
    if isinstance(platform_map, dict) and platform_name in platform_map:
        entry = platform_map[platform_name]
        if isinstance(entry, dict):
            kind = entry.get("kind")
            image = entry.get("image")
            if kind and image:
                return kind, image
    # Built-in: Arista EOS / cEOS / vEOS -> containerlab ceos
    version_str = sw_version.version if sw_version else "4.34.2F"
    if platform_name in ("eos", "ceos", "veos"):
        return "arista_ceos", f"ceos:{version_str}"
    # Default for unknown platform
    return "linux", "alpine:latest"


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

    nodes = {}
    for dev in devices:
        kind, image = _platform_to_clab_kind_image(dev)
        node_name = dev.name  # containerlab will use this as hostname
        node_cfg = {"kind": kind, "image": image}
        if device_startup_configs and dev.name in device_startup_configs:
            # Path relative to topology file (same directory on containerlab server)
            node_cfg["startup-config"] = device_startup_configs[dev.name]
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

    return _render_yaml(name, nodes, links)


def get_required_images_for_location(location):
    """
    Return the set of container image names (e.g. {"ceos:4.34.2F", "alpine:latest"})
    needed to deploy the topology for this location. Uses the same platform mapping as
    build_containerlab_yaml, so this can be used to verify images exist before deploy.
    """
    devices = list(Device.objects.filter(location=location))
    images = set()
    for dev in devices:
        _, image = _platform_to_clab_kind_image(dev)
        images.add(image)
    return images


def _empty_topology_yaml(location):
    name = re.sub(r"[^a-z0-9-]", "-", location.name.lower()).strip("-") or "lab"
    return _render_yaml(name, {}, [])


def _render_yaml(name, nodes, links):
    """Render containerlab topology dict to YAML string."""
    import yaml
    data = {
        "name": name,
        "topology": {
            "nodes": nodes or {"placeholder": {"kind": "linux", "image": "alpine:latest"}},
            "links": links,
        },
    }
    return yaml.dump(data, default_flow_style=False, sort_keys=False, allow_unicode=True)
