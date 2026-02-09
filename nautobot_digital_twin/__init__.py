"""App declaration for nautobot_digital_twin."""

from importlib import metadata

from nautobot.apps import NautobotAppConfig, nautobot_database_ready

__version__ = metadata.version(__name__)


class NautobotDigitalTwinConfig(NautobotAppConfig):
    """App configuration for the nautobot_digital_twin app."""

    name = "nautobot_digital_twin"
    verbose_name = "Nautobot Digital Twin"
    version = __version__
    author = "b@rtsmeding IT"
    description = "Nautobot Digital Twin."
    base_url = "nautobot-digital-twin"
    required_settings = []
    default_settings = {
        "BACKEND": "containerlab",
        "BACKEND_URLS": {},
        "LOCATION_TYPE_NAME": "Site",
        "CONTAINERLAB_SSH_HOST": "172.16.6.128",
        "CONTAINERLAB_SSH_PORT": 22,
        "CONTAINERLAB_SSH_USER": "clab",
        "CONTAINERLAB_SSH_PASSWORD": "clab",
        # Path on Nautobot (container/host) where topology YAML files are created/stored
        "DIGITAL_TWIN_ROOT": "/opt/nautobot/digital_twin",
        # Subfolder under the containerlab SSH user's home where topology files live (e.g. "nautobot" -> ~/nautobot)
        "CONTAINERLAB_REMOTE_TOPOLOGY_DIR": "nautobot",
        "CONTAINERLAB_SSH_CONNECT_TIMEOUT": 15,
        "CONTAINERLAB_COMMAND_TIMEOUT_MINUTES": 5,
        "DIGITAL_TWIN_JOB_TIMEOUT_MINUTES": 10,
        # Auto-destroy deployments after this many minutes (0 = disable). Default 24h.
        "DIGITAL_TWIN_AUTO_DESTROY_MINUTES": 1440,
        # Optional: map Nautobot platform name (lowercase) to containerlab kind/image.
        # e.g. {"eos": {"kind": "arista_ceos", "image": "ceos:4.34.2F"}}. When empty, built-in mapping is used (eos/ceos/veos -> ceos).
        "CONTAINERLAB_PLATFORM_MAP": {},
    }
    docs_view_name = "plugins:nautobot_digital_twin:docs"
    searchable_models = ["digitaltwindeployment"]
    jobs = "jobs"

    def ready(self):
        """Connect signals and run app-ready hooks."""
        super().ready()

        # Create Job Buttons once the database is ready and Jobs have been synced,
        # mirroring the pattern used by nautobot-app-golden-config.
        from nautobot_digital_twin import signals  # pylint:disable=import-outside-toplevel

        nautobot_database_ready.connect(signals.post_migrate_create_job_buttons, sender=self)

        # Existing startup logic (register jobs, DIGITAL_TWIN_ROOT checks, etc.).
        from nautobot_digital_twin.app_ready import run_ready  # pylint:disable=import-outside-toplevel

        run_ready()


config = NautobotDigitalTwinConfig  # pylint:disable=invalid-name
