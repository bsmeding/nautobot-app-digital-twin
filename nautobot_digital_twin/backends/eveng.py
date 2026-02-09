# Deploy on EveNG server

import logging
import paramiko

from .base import DigitalTwinBackend

logger = logging.getLogger(__name__)


class EveNGBackend(DigitalTwinBackend):
    """EveNG backend; uses backend_url from app config BACKEND_URLS if set."""
    