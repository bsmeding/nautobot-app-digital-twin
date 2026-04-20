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
      Ethernet1       -> eth1
      Ethernet1/2     -> eth1-2
      Management0     -> mgmt0
      Loopback0       -> lo0
      Port-channel1   -> po1
      GigabitEthernet0/1 -> ge-0-1
      FastEthernet0/1    -> fe-0-1
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
    """Return (kind, image) for containerlab node from Nautobot device platform/software_version."""
    platform = getattr(device, "platform", None)
    sw_version = getattr(device, "software_version", None)
    platform_name = (platform.name if platform else "").lower()
    platform_key = platform_name.replace(" ", "_")
    cfg = get_plugin_config()
    platform_map = cfg.get("CONTAINERLAB_PLATFORM_MAP") or {}
    strict_version = bool(cfg.get("USE_STRICT_SOFTWARE_VERSION", True))
    if isinstance(platform_map, dict):
        entry = platform_map.get(platform_name) or platform_map.get(platform_key)
        if entry is not None:
            if isinstance(entry, str):
                kind = _CLAB_IMAGE_TO_KIND.get(entry, platform_key or "linux")
                return kind, entry
            if isinstance(entry, dict):
                kind = entry.get("kind")
                image = entry.get("image")
                if kind and image:
                    return kind, image
    # Built-in: Arista EOS / cEOS / vEOS -> ceos
    if platform_name in ("eos", "ceos", "veos"):
        if strict_version:
            version_str = getattr(sw_version, "version", None)
            if not version_str:
                version_str = "4.34.2F"
            image = f"ceos:{version_str}"
        else:
            image = "ceos"
        return "arista_ceos", image
    # Default
    return "linux", "alpine:latest"


def build_containerlab_yaml(location, device_startup_configs=None, device_filter=None):
    """
    Build a containerlab topology YAML string for the given Location.

    device_startup_configs: optional dict mapping device name -> relative config filename.
    device_filter: optional dict of queryset filter kwargs applied to Device.objects.filter()
                   (e.g. {"role__name": "Leaf", "tags__name": "lab-ready"}) to deploy a subset.
    """
    qs = Device.objects.filter(location=location)
    if device_filter:
        qs = qs.filter(**device_filter)
    devices = list(qs.order_by("name"))
    if not devices:
        logger.warning("No devices at location %s (filter: %s); generating empty topology", location.name, device_filter)
        return _empty_topology_yaml(location)

    name = re.sub(r"[^a-z0-9-]", "-", location.name.lower()).strip("-") or "lab"

    nodes = {}
    for dev in devices:
        kind, image = _platform_to_clab_kind_image(dev)
        node_cfg = {"kind": kind, "image": image}
        if kind == "linux":
            node_cfg["cmd"] = "sleep infinity"
        if device_startup_configs and dev.name in device_startup_configs:
            node_cfg["startup-config"] = device_startup_configs[dev.name]
            node_cfg["enforce-startup-config"] = True
        nodes[dev.name] = node_cfg

    device_ids = {dev.id for dev in devices}
    interface_ct = ContentType.objects.get_for_model(Interface)
    interface_ids = list(
        Interface.objects.filter(device__id__in=device_ids).values_list("pk", flat=True)
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
            # Only include cables between devices that are in our filtered set
            if dev_a.id not in device_ids or dev_b.id not in device_ids:
                continue
            endpoint_a = f"{dev_a.name}:{_nautobot_iface_to_clab(if_a)}"
            endpoint_b = f"{dev_b.name}:{_nautobot_iface_to_clab(if_b)}"
            key = tuple(sorted([endpoint_a, endpoint_b]))
            if key in seen:
                continue
            seen.add(key)
            links.append({"endpoints": [endpoint_a, endpoint_b]})

    return _render_yaml(name, nodes, links)


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
        _, image = _platform_to_clab_kind_image(dev)
        images.add(image)
    return images


def build_mermaid_topology(location):
    """
    Build a Mermaid graph description for the given Location.
    Edges include interface labels (e.g. Ethernet1:Ethernet1) so the diagram is informative.

    Example output:

        graph LR
          spine1 ---|"Ethernet1 -- Ethernet1"| leaf1
          leaf1 ---|"Ethernet2 -- Ethernet1"| host1
    """
    devices = list(Device.objects.filter(location=location).order_by("name"))
    if not devices:
        return "graph LR\n  %% No devices at this location\n"

    device_names = {dev.id: dev.name for dev in devices}

    interface_ct = ContentType.objects.get_for_model(Interface)
    interface_ids = list(
        Interface.objects.filter(device__location=location).values_list("pk", flat=True)
    )
    # edges: (name_a, name_b, iface_a, iface_b) — deduplicated by sorted device pair
    edges = {}
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
            name_a = device_names.get(a.device.id)
            name_b = device_names.get(b.device.id)
            if not name_a or not name_b or name_a == name_b:
                continue
            key = tuple(sorted((name_a, name_b)))
            if key not in edges:
                # Store in sorted order so label reads left-device:iface -- right-device:iface
                if name_a <= name_b:
                    edges[key] = (name_a, name_b, a.name, b.name)
                else:
                    edges[key] = (name_b, name_a, b.name, a.name)

    lines = ["graph LR"]
    if not edges:
        for name in sorted(device_names.values()):
            lines.append(f"  {name}")
    else:
        for key in sorted(edges):
            dev_a, dev_b, if_a, if_b = edges[key]
            label = f"{if_a} -- {if_b}"
            lines.append(f'  {dev_a} ---| "{label}" |{dev_b}')
    return "\n".join(lines)


def _empty_topology_yaml(location):
    name = re.sub(r"[^a-z0-9-]", "-", location.name.lower()).strip("-") or "lab"
    return _render_yaml(name, {}, [])


def _render_yaml(name, nodes, links):
    """Render containerlab topology dict to YAML string."""
    import yaml
    data = {
        "name": name,
        "topology": {
            "nodes": nodes or {"placeholder": {"kind": "linux", "image": "alpine:latest", "cmd": "sleep infinity"}},
            "links": links,
        },
    }
    return yaml.dump(data, default_flow_style=False, sort_keys=False, allow_unicode=True)
