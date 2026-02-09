# Deploy on GNS3 server

import logging
import paramiko

from .base import DigitalTwinBackend

logger = logging.getLogger(__name__)


class Gns3Backend(DigitalTwinBackend):
    """GNS3 backend; uses backend_url from app config BACKEND_URLS if set."""
    