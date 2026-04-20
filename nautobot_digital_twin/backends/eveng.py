# Deploy on EVE-NG server via REST API (evengsdk)

import logging
import re

from django.contrib.contenttypes.models import ContentType
from nautobot.dcim.models import Cable, Device, Interface
from nautobot_digital_twin.plugin_config import get_plugin_config
from nautobot_digital_twin.secrets_utils import get_credentials_from_secrets_group

from .base import DigitalTwinBackend

logger = logging.getLogger(__name__)

# EVE-NG management network type (pnet1 = management)
EVENG_MGMT_NETWORK_TYPE = "pnet1"
EVENG_MGMT_NETWORK_NAME = "eve-mgmt"


def _device_platform_key(device):
    """Return platform key for config lookups (e.g. 'arista_eos')."""
    platform = getattr(device, "platform", None)
    name = (platform.name if platform else "").lower()
    return name.replace(" ", "_")


def _nautobot_iface_to_eveng(nautobot_name: str) -> str:
    """Map Nautobot interface name to EVE-NG port label.

    Ethernet1 -> Eth1, Ethernet2 -> Eth2, etc.
    Mgmt1 is used separately when connecting to management cloud.
    """
    match = re.match(r"^Ethernet(\d+)$", nautobot_name, re.IGNORECASE)
    if match:
        return f"Eth{match.group(1)}"
    # Fallback: capitalize first letter, strip
    cleaned = nautobot_name.replace(" ", "").replace("-", "")
    return cleaned or "Eth1"


def _platform_to_eveng_template_image(device):
    """Return (template, image) for EVE-NG node from Nautobot device platform.

    Uses EVENG_PLATFORM_MAP if set: platform_key -> template or {"template": str, "image": str}.
    Built-in: arista_eos/eos/ceos/veos -> veos with version from software_version.
    """
    platform = getattr(device, "platform", None)
    sw_version = getattr(device, "software_version", None)
    platform_name = (platform.name if platform else "").lower()
    platform_key = platform_name.replace(" ", "_")
    cfg = get_plugin_config()
    platform_map = cfg.get("EVENG_PLATFORM_MAP") or {}
    strict_version = bool(cfg.get("USE_STRICT_SOFTWARE_VERSION", True))

    if isinstance(platform_map, dict):
        entry = platform_map.get(platform_name) or platform_map.get(platform_key)
        if entry is not None:
            if isinstance(entry, str):
                # Simple: platform -> template (use default image from template)
                return entry, None
            if isinstance(entry, dict):
                return entry.get("template", "veos"), entry.get("image")

    # Built-in: Arista EOS / cEOS / vEOS -> veos
    if platform_name in ("eos", "ceos", "veos") or platform_key == "arista_eos":
        if strict_version and sw_version:
            version_str = getattr(sw_version, "version", None)
            if version_str:
                # vEOS image format: veos-4.22.0F, veos-4.34.2F
                image = f"veos-{version_str}"
                return "veos", image
        return "veos", None  # Use template default image

    # Default for unknown platform: user must configure EVENG_PLATFORM_MAP
    logger.warning(
        "Platform '%s' has no built-in EVE-NG mapping. Configure EVENG_PLATFORM_MAP.",
        platform_key or "unknown",
    )
    return "veos", None  # Fallback; may fail if veos not on EVE-NG server


class EveNGBackend(DigitalTwinBackend):
    """EVE-NG backend; uses REST API via evengsdk. Config: EVENG_* settings."""

    def _get_connection_params(self):
        """Return (host, protocol, port, user, password, ssl_verify) from config or Secrets Group."""
        cfg = get_plugin_config()
        host = cfg.get("EVENG_HOST", "localhost")
        protocol = (cfg.get("EVENG_PROTOCOL") or "https").lower()
        port = cfg.get("EVENG_PORT")  # None = default 443/80
        user = cfg.get("EVENG_USER", "admin")
        password = cfg.get("EVENG_PASSWORD", "eve")
        ssl_verify = bool(cfg.get("EVENG_SSL_VERIFY", False))

        secrets_group = (cfg.get("EVENG_CREDENTIALS_SECRETS_GROUP") or "").strip()
        if secrets_group:
            try:
                from nautobot.extras.choices import SecretsGroupAccessTypeChoices
                access_type = getattr(SecretsGroupAccessTypeChoices, "TYPE_GENERIC", "generic")
            except (ImportError, AttributeError):
                access_type = "generic"
            creds = get_credentials_from_secrets_group(secrets_group, access_type)
            if creds:
                user, password = creds
                logger.debug("Using EVE-NG credentials from Secrets Group '%s'", secrets_group)

        return host, protocol, port, user, password, ssl_verify

    def _get_client(self):
        """Create and return logged-in EvengClient."""
        from evengsdk.client import EvengClient

        host, protocol, port, user, password, ssl_verify = self._get_connection_params()
        client = EvengClient(
            host=host,
            protocol=protocol,
            port=port,
            ssl_verify=ssl_verify,
        )
        if not ssl_verify:
            client.disable_insecure_warnings()
        client.login(username=user, password=password)
        return client

    def _lab_path(self, site):
        """Return EVE-NG lab path (e.g. /nautobot/site-name)."""
        cfg = get_plugin_config()
        folder = (cfg.get("EVENG_LAB_FOLDER") or "nautobot").strip("/")
        lab_name = re.sub(r"[^a-z0-9-]", "-", site.name.lower()).strip("-") or "lab"
        return f"/{folder}/{lab_name}"

    def _build_topology(self, site, device_startup_configs=None):
        """Build topology data: nodes (name, template, image, config), links, device_mgmt_ips."""
        from nautobot_digital_twin.topology.containerlab import (
            _get_mgmt_from_devices,
        )

        devices = list(Device.objects.filter(location=site).order_by("name"))
        if not devices:
            return [], [], {}

        cfg = get_plugin_config()
        use_primary_ip = bool(cfg.get("USE_PRIMARY_IP_FOR_MGMT", True))
        device_mgmt_ips = {}
        if use_primary_ip:
            _, device_mgmt_ips = _get_mgmt_from_devices(devices)

        nodes = []
        for dev in devices:
            template, image = _platform_to_eveng_template_image(dev)
            config_content = None
            if device_startup_configs and dev.name in device_startup_configs:
                config_content = device_startup_configs.get(dev.name)
            nodes.append({
                "name": dev.name,
                "template": template,
                "image": image,
                "config": config_content,
            })

        # Build links from cables
        interface_ct = ContentType.objects.get_for_model(Interface)
        interface_ids = list(
            Interface.objects.filter(device__location=site).values_list("pk", flat=True)
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
                dev_a, if_a = a.device.name, a.name
                dev_b, if_b = b.device.name, b.name
                label_a = _nautobot_iface_to_eveng(if_a)
                label_b = _nautobot_iface_to_eveng(if_b)
                key = tuple(sorted([(dev_a, label_a), (dev_b, label_b)]))
                if key in seen:
                    continue
                seen.add(key)
                links.append((dev_a, label_a, dev_b, label_b))

        return nodes, links, device_mgmt_ips

    def check_health(self):
        """Check if EVE-NG API is reachable."""
        try:
            client = self._get_client()
            resp = client.api.get_server_status()
            client.logout()
            if resp.get("status") == "success" or "data" in resp:
                return True, "EVE-NG API is reachable"
        except Exception as e:
            logger.exception("EVE-NG health check failed: %s", e)
            return False, str(e)
        return False, "EVE-NG API check failed"

    def deploy_site(self, site, job=None, config_source="empty_config"):
        """Deploy digital twin on EVE-NG: create lab, add nodes, connect links, start nodes."""
        def log(msg, *args):
            if job:
                job.logger.info(msg, *args)
            logger.info(msg, *args)

        device_startup_configs = {}
        if config_source == "intended_config":
            try:
                from nautobot_digital_twin.golden_config_intended import get_device_intended_config
                from nautobot_digital_twin.config_filter import (
                    filter_config_remove_blocks,
                    filter_config_replace,
                    filter_config_append_add_lines,
                    build_minimal_config_from_add_lines,
                )
                from nautobot_digital_twin.secrets_utils import get_fallback_auth_credentials

                cfg = get_plugin_config()
                remove_patterns = cfg.get("REMOVE_CONFIG_LINES") or []
                platform_remove = cfg.get("PLATFORM_REMOVE_CONFIG_LINES") or {}
                replace_patterns = cfg.get("REPLACE_CONFIG_PATTERNS") or []
                platform_add = cfg.get("PLATFORM_ADD_CONFIG_LINES") or cfg.get("PLATFORM_FALLBACK_AUTH") or {}
                username, password = get_fallback_auth_credentials()

                devices = list(Device.objects.filter(location=site).order_by("name"))
                for device in devices:
                    config_content = get_device_intended_config(device)
                    platform_key = _device_platform_key(device)
                    has_platform_add = platform_key in platform_add

                    if not config_content and has_platform_add:
                        config_content = build_minimal_config_from_add_lines(
                            platform_key, username, password, platform_add
                        )
                        log("No intended config for %s; created minimal config.", device.name)
                    elif not config_content:
                        continue

                    all_remove = list(remove_patterns) + list(platform_remove.get(platform_key) or [])
                    if all_remove:
                        config_content = filter_config_remove_blocks(config_content, all_remove)
                    if replace_patterns:
                        config_content = filter_config_replace(config_content, replace_patterns)
                    if has_platform_add and config_content:
                        config_content = filter_config_append_add_lines(
                            config_content, platform_key, username, password, platform_add
                        )
                    device_startup_configs[device.name] = config_content
            except ImportError as e:
                log("Golden Config not available; deploying with empty config: %s", e)

        log("Building topology for %s...", site.name)
        nodes, links, device_mgmt_ips = self._build_topology(site, device_startup_configs)

        if not nodes:
            log("No devices at location %s; nothing to deploy.", site.name)
            return 1, "", "No devices at this location"

        lab_path = self._lab_path(site)
        lab_name = lab_path.split("/")[-1]

        try:
            client = self._get_client()
            api = client.api

            # Check if lab already exists; delete to allow recreate
            try:
                existing = api.get_lab(lab_path)
                if existing.get("status") == "success" or "data" in existing:
                    log("Lab already exists; deleting before recreate...")
                    api.delete_lab(lab_path)
            except Exception:
                pass

            log("Creating lab %s...", lab_path)
            folder = lab_path.rsplit("/", 1)[0] or "/"
            if folder == "/":
                folder = ""
            resp = api.create_lab(name=lab_name, path=folder or "/", description=f"Nautobot Digital Twin: {site.name}")
            if resp.get("status") != "success" and "data" not in resp:
                raise RuntimeError(f"Failed to create lab: {resp}")

            # Add management network
            log("Adding management network...")
            api.add_lab_network(lab_path, network_type=EVENG_MGMT_NETWORK_TYPE, name=EVENG_MGMT_NETWORK_NAME)

            # Add nodes
            left = 50
            for node in nodes:
                log("Adding node %s (template=%s)...", node["name"], node["template"])
                api.add_node(
                    lab_path,
                    template=node["template"],
                    name=node["name"],
                    image=node["image"],
                    left=left,
                    top=50,
                )
                left += 150

            # Connect nodes to management network
            for node in nodes:
                log("Connecting %s to management...", node["name"])
                api.connect_node_to_cloud(lab_path, node["name"], "Mgmt1", EVENG_MGMT_NETWORK_NAME)

            # Connect node-to-node links
            for dev_a, label_a, dev_b, label_b in links:
                log("Connecting %s:%s <-> %s:%s", dev_a, label_a, dev_b, label_b)
                api.connect_node_to_node(lab_path, dev_a, label_a, dev_b, label_b)

            # Upload configs if intended_config
            if device_startup_configs:
                nodes_data = api.list_nodes(lab_path)
                node_map = nodes_data.get("data", {}) or {}
                for node in nodes:
                    if node.get("config"):
                        for nid, node_info in node_map.items():
                            if node_info.get("name") == node["name"]:
                                log("Uploading config for %s...", node["name"])
                                api.upload_node_config(lab_path, str(nid), node["config"])
                                api.enable_node_config(lab_path, str(nid))
                                break

            # Start all nodes
            log("Starting all nodes...")
            api.start_all_nodes(lab_path)

            client.logout()
            log("EVE-NG deployment completed for %s", site.name)
            return 0, "", ""

        except Exception as e:
            logger.exception("EVE-NG deploy failed: %s", e)
            raise

    def destroy_site(self, site):
        """Stop nodes and delete lab on EVE-NG."""
        lab_path = self._lab_path(site)
        try:
            client = self._get_client()
            api = client.api
            try:
                api.stop_all_nodes(lab_path)
            except Exception as e:
                logger.warning("Stop nodes failed (lab may not exist): %s", e)
            api.delete_lab(lab_path)
            client.logout()
            return 0, "", ""
        except Exception as e:
            logger.exception("EVE-NG destroy failed: %s", e)
            return 1, "", str(e)
