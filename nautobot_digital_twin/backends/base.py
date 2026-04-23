# nautobot_digital_twin/backends/base.py
from abc import ABC, abstractmethod

from nautobot.apps.jobs import JobHookReceiver, register_jobs

class DigitalTwinBackend(ABC):
    """Abstract interface for all digital twin backends."""

    def __init__(self, backend_url=None):
        """
        backend_url: optional URL for Containerlab from app config BACKEND_URLS["containerlab"].
        """
        self.backend_url = backend_url

    @abstractmethod
    def deploy_site(self, site, job=None, config_source="empty_config"):
        """Start a digital twin for the given Site/Location.

        job: optional Nautobot job for logging. config_source: 'empty_config' or 'intended_config'.
        """
        raise NotImplementedError

    @abstractmethod
    def destroy_site(self, site):
        """Tear down the digital twin for the given Site/Location."""
        raise NotImplementedError

