# nautobot_digital_twin/backends/__init__.py
from nautobot_digital_twin.utils import get_plugin_config

from .base import DigitalTwinBackend
from .containerlab import ContainerlabBackend


_BACKENDS = {
    "containerlab": ContainerlabBackend,
}


def get_available_backend_names():
    """Return list of registered backend names (stable order). First is the default."""
    return list(_BACKENDS.keys())


def get_backend(name=None) -> DigitalTwinBackend:
    """Return an instance of the given or configured backend (with URL from config if set)."""
    cfg = get_plugin_config()
    backend_name = name if name is not None else cfg.get("BACKEND", "containerlab")
    backend_cls = _BACKENDS.get(backend_name)
    if backend_cls is None:
        raise ValueError(f"Unknown digital twin backend: {backend_name}")
    backend_urls = cfg.get("BACKEND_URLS") or {}
    backend_url = backend_urls.get(backend_name) if isinstance(backend_urls, dict) else None
    return backend_cls(backend_url=backend_url)