# nautobot_digital_twin/backends/__init__.py
import logging

from nautobot_digital_twin.utils import get_plugin_config

from .base import DigitalTwinBackend
from .containerlab import ContainerlabBackend

logger = logging.getLogger(__name__)

_DEFAULT_BACKEND = "containerlab"
_BACKENDS = {
    _DEFAULT_BACKEND: ContainerlabBackend,
}


def get_available_backend_names():
    """Return list of registered backend names (stable order). First is the default."""
    return list(_BACKENDS.keys())


def get_backend(name=None) -> DigitalTwinBackend:
    """Return the Containerlab backend (only supported implementation)."""
    cfg = get_plugin_config()
    requested = name if name is not None else cfg.get("BACKEND", _DEFAULT_BACKEND)
    if not isinstance(requested, str):
        requested = str(requested)
    requested_norm = requested.strip().lower()
    if requested_norm != _DEFAULT_BACKEND:
        logger.warning(
            "Digital Twin backend %r is not supported (only %r is available); using %r.",
            requested,
            _DEFAULT_BACKEND,
            _DEFAULT_BACKEND,
        )
    backend_cls = _BACKENDS[_DEFAULT_BACKEND]
    backend_urls = cfg.get("BACKEND_URLS") or {}
    backend_url = backend_urls.get(_DEFAULT_BACKEND) if isinstance(backend_urls, dict) else None
    return backend_cls(backend_url=backend_url)
