# nautobot_digital_twin/backends/__init__.py
"""Backend registry for digital twin deploy/destroy adapters."""

import logging

from nautobot_digital_twin.plugin_config import get_plugin_config

from .base import DigitalTwinBackend
from .containerlab import ContainerlabBackend
from .eveng import EveNGBackend

logger = logging.getLogger(__name__)

_DEFAULT_BACKEND = "containerlab"
_BACKENDS = {
    "containerlab": ContainerlabBackend,
    "eve-ng": EveNGBackend,
    "eveng": EveNGBackend,  # alias
}


def get_available_backend_names():
    """Return registered backend names (stable order, aliases omitted)."""
    return ["containerlab", "eve-ng"]


def get_configured_backend_name():
    """Return the configured backend name (normalized), defaulting to containerlab."""
    cfg = get_plugin_config()
    requested = cfg.get("BACKEND", _DEFAULT_BACKEND)
    if not isinstance(requested, str):
        requested = str(requested)
    name = requested.strip().lower()
    if name == "eveng":
        return "eve-ng"
    return name or _DEFAULT_BACKEND


def get_backend(name=None) -> DigitalTwinBackend:
    """Return a backend instance by name, or the configured default."""
    cfg = get_plugin_config()
    if name is None:
        requested = get_configured_backend_name()
    else:
        requested = str(name).strip().lower() or _DEFAULT_BACKEND

    if requested not in _BACKENDS:
        available = ", ".join(get_available_backend_names())
        raise ValueError(f"Digital Twin backend {requested!r} is not supported. Available: {available}.")

    canonical = "eve-ng" if requested in {"eve-ng", "eveng"} else requested
    backend_cls = _BACKENDS[requested]
    backend_urls = cfg.get("BACKEND_URLS") or {}
    backend_url = None
    if isinstance(backend_urls, dict):
        backend_url = backend_urls.get(canonical) or backend_urls.get(requested)
    return backend_cls(backend_url=backend_url)


__all__ = [
    "DigitalTwinBackend",
    "ContainerlabBackend",
    "EveNGBackend",
    "get_available_backend_names",
    "get_configured_backend_name",
    "get_backend",
]
