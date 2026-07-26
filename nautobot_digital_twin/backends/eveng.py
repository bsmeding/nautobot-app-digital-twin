# nautobot_digital_twin/backends/eveng.py
"""EVE-NG REST API backend for digital twin deploy/destroy."""

from __future__ import annotations

import json
import logging
from contextlib import contextmanager
from typing import Any
from urllib.parse import quote, urljoin

import requests

from nautobot_digital_twin.plugin_config import get_plugin_config
from nautobot_digital_twin.secrets_utils import get_credentials_from_secrets_group
from nautobot_digital_twin.topology.eveng import build_eveng_lab_plan, match_eve_interface, sanitize_lab_name

from .base import DigitalTwinBackend

logger = logging.getLogger(__name__)


def _get_generic_access_type():
    try:
        from nautobot.extras.choices import SecretsGroupAccessTypeChoices

        return getattr(SecretsGroupAccessTypeChoices, "TYPE_GENERIC", "generic")
    except (ImportError, AttributeError):
        return "generic"


class EveNGBackend(DigitalTwinBackend):
    """Deploy disposable labs to EVE-NG (Community or Pro) via REST API."""

    name = "eve-ng"
    supports_intended_config = False
    supports_connectivity_tests = False

    def get_connection_params(self):
        """Return (base_url, user, password, verify_ssl, timeout) from config / secrets."""
        cfg = get_plugin_config()
        base_url = (self.backend_url or cfg.get("EVE_NG_URL") or "").rstrip("/")
        if not base_url:
            raise ValueError(
                "EVE-NG backend requires EVE_NG_URL or BACKEND_URLS['eve-ng'] (e.g. https://eve.example.com)."
            )
        user = cfg.get("EVE_NG_USER", "admin")
        password = cfg.get("EVE_NG_PASSWORD", "eve")
        secrets_group = (cfg.get("EVE_NG_CREDENTIALS_SECRETS_GROUP") or "").strip()
        if secrets_group:
            creds = get_credentials_from_secrets_group(secrets_group, _get_generic_access_type())
            if creds:
                user, password = creds
                logger.debug("Using EVE-NG credentials from Secrets Group '%s'", secrets_group)
        verify_ssl = bool(cfg.get("EVE_NG_VERIFY_SSL", False))
        timeout = int(cfg.get("EVE_NG_REQUEST_TIMEOUT", 60))
        return base_url, user, password, verify_ssl, timeout

    def _lab_folder(self) -> str:
        cfg = get_plugin_config()
        folder = (cfg.get("EVE_NG_LAB_FOLDER") or "/nautobot").strip() or "/nautobot"
        if not folder.startswith("/"):
            folder = f"/{folder}"
        return folder.rstrip("/") or "/"

    def _lab_path(self, site) -> str:
        """Return API path segment like /nautobot/SiteName.unl (URL-encoded later)."""
        lab_name = sanitize_lab_name(site.name)
        folder = self._lab_folder()
        if folder == "/":
            return f"/{lab_name}.unl"
        return f"{folder}/{lab_name}.unl"

    def _encode_lab_path(self, lab_path: str) -> str:
        """Encode each path segment for use in /api/labs/... URLs."""
        parts = [p for p in lab_path.split("/") if p]
        return "/" + "/".join(quote(p, safe="") for p in parts)

    @contextmanager
    def _session(self):
        """Authenticated requests session (cookie login). Yields conn=(session, base_url, timeout)."""
        base_url, user, password, verify_ssl, timeout = self.get_connection_params()
        session = requests.Session()
        session.verify = verify_ssl
        login_url = urljoin(base_url + "/", "api/auth/login")
        payload = {"username": user, "password": password, "html5": "-1"}
        resp = session.post(login_url, json=payload, timeout=timeout)
        resp.raise_for_status()
        body = resp.json() if resp.content else {}
        if body.get("status") not in (None, "success"):
            raise RuntimeError(f"EVE-NG login failed: {body.get('message') or body}")
        try:
            yield (session, base_url, timeout)
        finally:
            try:
                session.get(urljoin(base_url + "/", "api/auth/logout"), timeout=timeout)
            except Exception as exc:  # noqa: BLE001 - best-effort logout
                logger.debug("EVE-NG logout ignored: %s", exc)
            session.close()

    def _api(self, conn, method: str, path: str, payload: dict | None = None) -> dict[str, Any]:
        session, base_url, timeout = conn
        url = urljoin(base_url + "/", path.lstrip("/"))
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        resp = session.request(
            method.upper(),
            url,
            headers=headers,
            data=json.dumps(payload) if payload is not None else None,
            timeout=timeout,
        )
        try:
            data = resp.json() if resp.content else {}
        except ValueError:
            data = {"message": resp.text, "status": "fail"}
        if resp.status_code >= 400:
            raise RuntimeError(
                f"EVE-NG API {method.upper()} {path} failed ({resp.status_code}): {data.get('message') or data}"
            )
        if isinstance(data, dict) and data.get("status") == "fail":
            raise RuntimeError(f"EVE-NG API {method.upper()} {path} failed: {data.get('message') or data}")
        return data if isinstance(data, dict) else {"data": data}

    def check_health(self):
        """Check EVE-NG API reachability via /api/status."""
        try:
            with self._session() as conn:
                data = self._api(conn, "GET", "api/status")
                version = (data.get("data") or {}).get("version") or "unknown"
                return True, f"EVE-NG OK (version {version}) at {conn[1]}"
        except Exception as exc:  # noqa: BLE001
            return False, str(exc)

    def get_topology_status(self, site):
        """List node statuses for the Location lab."""
        lab_path = self._encode_lab_path(self._lab_path(site))
        try:
            with self._session() as conn:
                data = self._api(conn, "GET", f"api/labs{lab_path}/nodes")
                nodes = data.get("data") or {}
                lines = []
                for node in nodes.values() if isinstance(nodes, dict) else []:
                    status = node.get("status")
                    state = {0: "stopped", 1: "starting", 2: "running", 3: "stopping"}.get(status, str(status))
                    lines.append(f"{node.get('name')}: {state} (id={node.get('id')}, template={node.get('template')})")
                out = "\n".join(lines) if lines else "(no nodes)"
                return 0, out, ""
        except Exception as exc:  # noqa: BLE001
            return 1, "", str(exc)

    def _ensure_folder(self, conn):
        folder = self._lab_folder()
        if folder in {"", "/"}:
            return
        parts = [p for p in folder.split("/") if p]
        current = "/"
        for part in parts:
            parent = current if current != "/" else "/"
            list_path = "api/folders" if parent == "/" else f"api/folders{self._encode_lab_path(parent)}"
            try:
                listing = self._api(conn, "GET", list_path)
            except RuntimeError:
                listing = {"data": {"folders": {}}}
            folders = ((listing.get("data") or {}).get("folders")) or {}
            names = {str(v.get("name") if isinstance(v, dict) else k).lower() for k, v in folders.items()}
            if part.lower() not in names:
                payload = {"path": parent if parent != "/" else "/", "name": part}
                self._api(conn, "POST", "api/folders", payload)
            current = f"/{part}" if parent == "/" else f"{parent}/{part}"

    def _delete_lab_if_exists(self, conn, site):
        lab_path = self._encode_lab_path(self._lab_path(site))
        try:
            self._api(conn, "GET", f"api/labs{lab_path}/nodes/stop")
        except Exception as exc:  # noqa: BLE001
            logger.debug("Stop before replace ignored for %s: %s", lab_path, exc)
        try:
            self._api(conn, "DELETE", f"api/labs{lab_path}")
            logger.info("Deleted existing EVE-NG lab %s", lab_path)
        except Exception as exc:  # noqa: BLE001
            logger.debug("Delete before replace ignored for %s: %s", lab_path, exc)

    def _create_lab(self, conn, site, lab_name):
        folder = self._lab_folder()
        payload = {
            "path": folder if folder != "/" else "/",
            "name": lab_name,
            "version": "1",
            "author": "nautobot-digital-twin",
            "description": f"Digital twin for Nautobot location {site.name}",
            "body": "Generated by nautobot-app-digital-twin",
        }
        self._api(conn, "POST", "api/labs", payload)

    def _add_node(self, conn, lab_path, spec: dict) -> int:
        payload = {
            "template": spec["template"],
            "type": spec.get("type", "qemu"),
            "name": spec.get("name"),
            "left": spec.get("left", "40%"),
            "top": spec.get("top", "40%"),
            "console": spec.get("console", "telnet"),
            "config": spec.get("config", "Unconfigured"),
            "delay": int(spec.get("delay", 0)),
        }
        for key in ("image", "icon", "ram", "cpu", "ethernet", "serial", "nvram", "uuid"):
            if spec.get(key) is not None:
                payload[key] = spec[key]
        data = self._api(conn, "POST", f"api/labs{lab_path}/nodes", payload)
        node_id = data.get("data", {}).get("id") if isinstance(data.get("data"), dict) else data.get("id")
        if node_id is not None:
            return int(node_id)
        nodes = self._api(conn, "GET", f"api/labs{lab_path}/nodes").get("data") or {}
        for node in nodes.values() if isinstance(nodes, dict) else []:
            if str(node.get("name", "")).lower() == str(spec.get("name", "")).lower():
                return int(node["id"])
        raise RuntimeError(f"Could not determine EVE-NG node id for {spec.get('name')}")

    def _list_networks(self, conn, lab_path) -> dict:
        data = self._api(conn, "GET", f"api/labs{lab_path}/networks")
        return data.get("data") or {}

    def _add_bridge(self, conn, lab_path, name: str) -> int:
        before = set(str(k) for k in self._list_networks(conn, lab_path).keys())
        payload = {"type": "bridge", "name": name, "visibility": "0"}
        data = self._api(conn, "POST", f"api/labs{lab_path}/networks", payload)
        net_id = None
        if isinstance(data.get("data"), dict):
            net_id = data["data"].get("id")
        net_id = net_id or data.get("id")
        if net_id is not None:
            return int(net_id)
        after = self._list_networks(conn, lab_path)
        for key, net in after.items():
            if str(key) not in before:
                return int(net.get("id") or key)
            if isinstance(net, dict) and net.get("name") == name:
                return int(net.get("id") or key)
        raise RuntimeError(f"Could not determine network id for bridge {name}")

    def _connect_interface(self, conn, lab_path, node_id: int, intf_index: int, net_id: int):
        payload = {str(intf_index): str(net_id)}
        self._api(conn, "PUT", f"api/labs{lab_path}/nodes/{node_id}/interfaces", payload)

    def _first_free_interface(self, ethernet_ifaces: list) -> tuple[int, dict] | None:
        for idx, intf in enumerate(ethernet_ifaces or []):
            if not isinstance(intf, dict):
                return idx, {"name": str(intf)}
            if int(intf.get("network_id") or 0) == 0:
                return idx, intf
        return None

    def _ethernet_list(self, ifaces_payload: dict) -> list:
        ethernet = (ifaces_payload or {}).get("ethernet") or []
        if isinstance(ethernet, dict):
            return [ethernet[k] for k in sorted(ethernet, key=int)]
        return ethernet

    def _wire_link(self, conn, lab_path, node_ids: dict, link: dict, log):
        a_name, z_name = link["a_device"], link["z_device"]
        a_id, z_id = node_ids.get(a_name), node_ids.get(z_name)
        if a_id is None or z_id is None:
            log("Skipping link %s: missing node id", link["name"])
            return

        a_eth = self._ethernet_list(self._api(conn, "GET", f"api/labs{lab_path}/nodes/{a_id}/interfaces").get("data"))
        z_eth = self._ethernet_list(self._api(conn, "GET", f"api/labs{lab_path}/nodes/{z_id}/interfaces").get("data"))

        a_match = match_eve_interface(link["a_iface"], a_eth) or self._first_free_interface(a_eth)
        z_match = match_eve_interface(link["z_iface"], z_eth) or self._first_free_interface(z_eth)
        if not a_match or not z_match:
            log(
                "Skipping link %s: could not map interfaces %s:%s <-> %s:%s",
                link["name"],
                a_name,
                link["a_iface"],
                z_name,
                link["z_iface"],
            )
            return

        net_id = self._add_bridge(conn, lab_path, link["name"])
        self._connect_interface(conn, lab_path, a_id, a_match[0], net_id)
        self._connect_interface(conn, lab_path, z_id, z_match[0], net_id)
        log("Linked %s:%s <-> %s:%s via bridge %s", a_name, link["a_iface"], z_name, link["z_iface"], net_id)

    def deploy_site(self, site, job=None, config_source="empty_config"):
        """Create lab from Nautobot topology, add nodes/links, start all nodes."""

        def log(msg, *args):
            if job:
                job.logger.info(msg, *args)
            logger.info(msg, *args)

        if config_source == "intended_config":
            log(
                "EVE-NG backend does not yet push intended configs during deploy; "
                "nodes will start Unconfigured. Set config_source=empty_config to silence this note."
            )

        plan = build_eveng_lab_plan(site)
        lab_name = plan["lab_name"]
        lab_path = self._encode_lab_path(self._lab_path(site))

        with self._session() as conn:
            log("Ensuring EVE-NG folder %s exists...", self._lab_folder())
            self._ensure_folder(conn)
            log("Replacing any existing lab at %s...", lab_path)
            self._delete_lab_if_exists(conn, site)
            log("Creating lab '%s'...", lab_name)
            self._create_lab(conn, site, lab_name)

            node_ids = {}
            for node in plan["nodes"]:
                spec = node["spec"]
                log("Adding node %s (template=%s)...", spec.get("name"), spec.get("template"))
                node_ids[node["device_name"]] = self._add_node(conn, lab_path, spec)

            for link in plan["links"]:
                self._wire_link(conn, lab_path, node_ids, link, log)

            log("Starting all nodes in %s...", lab_path)
            self._api(conn, "GET", f"api/labs{lab_path}/nodes/start")
            msg = f"EVE-NG lab deployed: {lab_path} ({len(node_ids)} nodes, {len(plan['links'])} links)"
            log(msg)
            return 0, msg, ""

    def destroy_site(self, site):
        """Stop nodes and delete the Location lab."""
        lab_path = self._encode_lab_path(self._lab_path(site))
        with self._session() as conn:
            try:
                self._api(conn, "GET", f"api/labs{lab_path}/nodes/stop")
            except Exception as exc:  # noqa: BLE001
                logger.warning("Stop nodes before destroy: %s", exc)
            try:
                self._api(conn, "DELETE", f"api/labs{lab_path}")
                return 0, f"Deleted EVE-NG lab {lab_path}", ""
            except Exception as exc:  # noqa: BLE001
                err = str(exc).lower()
                if "not found" in err or "60022" in err or "does not exist" in err:
                    return 0, f"Lab already gone: {lab_path}", ""
                return 1, "", str(exc)

    def push_intended_config(self, site, job=None):
        return 1, "", "EVE-NG backend does not yet support push intended config (planned for a later release)."
