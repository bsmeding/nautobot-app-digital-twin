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
    base_url = "nautobot-app-digital-twin"
    required_settings = []
    default_settings = {
        "BACKEND": "containerlab",
        "BACKEND_URLS": {},
        "LOCATION_TYPE_NAME": "Site",
        # When True, containerlab images use the exact Nautobot software_version
        # (e.g. ceos:4.34.2F). When False, omit the tag so the backend uses the
        # default/latest image tag (e.g. ceos).
        "USE_STRICT_SOFTWARE_VERSION": True,
        "CONTAINERLAB_SSH_HOST": "172.16.6.128",
        "CONTAINERLAB_SSH_PORT": 22,
        "CONTAINERLAB_SSH_USER": "clab",
        "CONTAINERLAB_SSH_PASSWORD": "clab",
        # Optional: path to SSH private key file. When set (and file exists), used instead of password.
        "CONTAINERLAB_SSH_KEY_PATH": "",
        # Optional: name of a Nautobot Secrets Group for SSH credentials (access type SSH, secret types Username/Password).
        # When set, overrides CONTAINERLAB_SSH_USER and CONTAINERLAB_SSH_PASSWORD.
        "CONTAINERLAB_SSH_CREDENTIALS_SECRETS_GROUP": "",
        # Optional: name of a Nautobot Secrets Group for digital twin fallback auth (access type Generic, Username/Password).
        # Used when appending platform-specific fallback auth to intended configs.
        # Optional: Secrets Group (access type Generic, Username/Password) for {username}/{password} in PLATFORM_ADD_CONFIG_LINES.
        "DIGITAL_TWIN_FALLBACK_AUTH_SECRETS_GROUP": "",
        # Replace patterns in intended config (e.g. for enterprises: switch radius/tacacs to local).
        # List of (old_string, new_string) tuples. E.g. [("group radius", "local"), ("group tacacs+", "local")].
        "REPLACE_CONFIG_PATTERNS": [],
        # Platform-specific config lines to add (e.g. fallback auth). Dict: platform_key -> list of lines.
        # Use {username} and {password} placeholders. E.g. {"arista_eos": ["username {username} privilege 15 role network-admin secret {password}"]}.
        "PLATFORM_ADD_CONFIG_LINES": {},
        # Platform-specific remove patterns. Dict: platform_key -> list of patterns (same format as REMOVE_CONFIG_LINES).
        # Applied in addition to global REMOVE_CONFIG_LINES. E.g. {"cisco_ios": ["radius-server"], "arista_eos": []}.
        "PLATFORM_REMOVE_CONFIG_LINES": {},
        # Path on Nautobot (container/host) where topology YAML files are created/stored
        "DIGITAL_TWIN_ROOT": "/opt/nautobot/digital_twin",
        # Subfolder under the containerlab SSH user's home where topology files live (e.g. "nautobot" -> ~/nautobot)
        "CONTAINERLAB_REMOTE_TOPOLOGY_DIR": "nautobot",
        "CONTAINERLAB_SSH_CONNECT_TIMEOUT": 15,
        # Increase for large topologies (each Arista cEOS ~2-3 min boot). 6 nodes ~15 min.
        "CONTAINERLAB_COMMAND_TIMEOUT_MINUTES": 5,
        "DIGITAL_TWIN_JOB_TIMEOUT_MINUTES": 10,
        # Auto-destroy deployments after this many minutes (0 = disable). Default 24h.
        "DIGITAL_TWIN_AUTO_DESTROY_MINUTES": 1440,
        # Optional: map Nautobot platform name (lowercase) to containerlab image.
        # Simple format: platform -> image (e.g. {"arista_eos": "ceos", "cisco_ios": "ios"}).
        # When empty, built-in mapping is used (eos/ceos/veos -> ceos).
        "CONTAINERLAB_PLATFORM_MAP": {},
        # When True, use Nautobot primary_ip4 for containerlab mgmt network (extract subnet, set mgmt-ipv4 per node).
        "USE_PRIMARY_IP_FOR_MGMT": True,
        # Remove config blocks from intended config before digital twin deploy.
        # When a line contains a pattern, that line and all indented children are removed.
        # E.g. ["GigabitEthernet0/0", "radius-server"] removes management interface and RADIUS blocks.
        "REMOVE_CONFIG_LINES": [],
        # When True (default), remove site folder (topology + config files) from backend on destroy.
        "DELETE_CONFIG_AFTER_DESTROY": True,
        # Platform-specific config for "Push intended config" job: where to copy config inside container
        # and optional reload command. Dict: platform_key -> {"container_path": str, "reload_command": str}.
        "PLATFORM_PUSH_CONFIG": {
            "arista_eos": {
                "container_path": "/mnt/flash/startup-config",
                "reload_command": "FastCli -p 15 -c 'configure replace flash:startup-config force'",
            },
            "cisco_ios": {
                "container_path": "/config/startup-config.cfg",
                "reload_command": "",
            },
        },
        # Maximum number of simultaneously active deployments per user (0 = unlimited).
        "MAX_DEPLOYMENTS_PER_USER": 0,
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
