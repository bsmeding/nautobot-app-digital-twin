# nautobot_digital_twin/backends/base.py
"""Abstract interface for digital twin deployment backends."""

from abc import ABC, abstractmethod


class DigitalTwinBackend(ABC):
    """Abstract interface for all digital twin backends."""

    name = "base"
    supports_intended_config = False
    supports_connectivity_tests = False

    def __init__(self, backend_url=None):
        """
        backend_url: optional URL for this backend from app config BACKEND_URLS[<name>].
        """
        self.backend_url = backend_url

    @abstractmethod
    def deploy_site(self, site, job=None, config_source="empty_config"):
        """Start a digital twin for the given Site/Location.

        job: optional Nautobot job for logging. config_source: 'empty_config' or 'intended_config'.
        Returns None or (exit_status, stdout, stderr).
        """
        raise NotImplementedError

    @abstractmethod
    def destroy_site(self, site):
        """Tear down the digital twin for the given Site/Location.

        Returns None or (exit_status, stdout, stderr).
        """
        raise NotImplementedError

    def check_health(self):
        """Return (ok: bool, message: str) for backend reachability."""
        return False, f"Backend '{self.name}' does not implement health checks."

    def get_topology_status(self, site):
        """Inspect running topology for site. Returns (exit_status, out, err)."""
        return 1, "", f"Backend '{self.name}' does not implement topology status."

    def push_intended_config(self, site, job=None):
        """Push Golden Config intended configs to a running twin. Returns (exit_status, out, err)."""
        return 1, "", f"Backend '{self.name}' does not support push intended config."

    def ping_from_node(self, node_name, target_ip, count=3, timeout_sec=2):
        """Ping target_ip from a running node. Returns (exit_status, out, err)."""
        return 1, "", f"Backend '{self.name}' does not support connectivity tests."
