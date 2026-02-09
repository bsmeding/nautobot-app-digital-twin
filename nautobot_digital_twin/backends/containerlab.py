# nautobot_digital_twin/backends/containerlab.py
import io
import logging
import os
import re
import paramiko

from nautobot.dcim.models import Device
from nautobot_digital_twin.plugin_config import get_plugin_config
from nautobot_digital_twin.topology import build_containerlab_yaml, get_required_images_for_location

from .base import DigitalTwinBackend

logger = logging.getLogger(__name__)


class ContainerlabBackend(DigitalTwinBackend):
    """Containerlab backend; uses backend_url from app config BACKEND_URLS if set."""

    def get_connection_params(self):
        """Return (host, port, user, password, key_path) from plugin config. Does not open a connection."""
        cfg = get_plugin_config()
        host = cfg["CONTAINERLAB_SSH_HOST"]
        port = cfg.get("CONTAINERLAB_SSH_PORT", 22)
        user = cfg.get("CONTAINERLAB_SSH_USER", "clab")
        password = cfg.get("CONTAINERLAB_SSH_PASSWORD", "clab")
        key_path = cfg.get("CONTAINERLAB_SSH_KEY_PATH", "")
        return host, port, user, password, key_path

    def _run_remote(self, command: str, timeout: int = None):
        """Run command over SSH. timeout: seconds to wait for command (from config if None)."""
        # Get config from nautobot_config.py
        cfg = get_plugin_config()
        # Set connection timeout
        connect_timeout = int(cfg.get("CONTAINERLAB_SSH_CONNECT_TIMEOUT", 15))
        # Set task timeout
        if timeout is None:
            timeout = int(cfg.get("CONTAINERLAB_COMMAND_TIMEOUT_MINUTES", 5)) * 60
        # Get connection parameters
        host, port, user, password, key_path = self.get_connection_params()
        logger.info("Connecting to %s:%s (connect_timeout=%ss)", host, port, connect_timeout)

        # Create paramiko client
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        try:
            # Connect to remote host using SSH key if provided, otherwise use password
            if key_path and os.path.exists(key_path):
                client.connect(
                    hostname=host, port=port, username=user, key_filename=key_path,
                    timeout=connect_timeout,
                )
            else:
                client.connect(
                    hostname=host, port=port, username=user, password=password,
                    timeout=connect_timeout,
                )
        except Exception as e:
            logger.error("SSH connect to %s:%s failed: %s", host, port, e)
            raise
        logger.info("Running remote command (timeout=%ss): %s", timeout, command)
        try:
            stdin, stdout, stderr = client.exec_command(command, timeout=timeout)
            exit_status = stdout.channel.recv_exit_status()
            out = stdout.read().decode()
            err = stderr.read().decode()
            logger.info("Command finished with exit_status=%s", exit_status)
            if err:
                logger.debug("stderr: %s", err)
            return exit_status, out, err
        except Exception as e:
            logger.error("Failed to execute command on %s: %s", host, e)
            raise
        finally:
            client.close()

    def check_health(self):
        """Check if containerlab is installed on the remote host (uses _run_remote, which opens SSH)."""
        cmd = "containerlab version"
        exit_status, out, err = self._run_remote(cmd)
        host, port, _, _, _ = self.get_connection_params()
        if exit_status != 0:
            return False, f"Containerlab is not installed on {host}"
        return True, f"Containerlab is installed on {host}"

    def _remote_topology_subdir(self):
        """Subdir under SSH user home for topology files (CONTAINERLAB_REMOTE_TOPOLOGY_DIR)."""
        cfg = get_plugin_config()
        return (cfg.get("CONTAINERLAB_REMOTE_TOPOLOGY_DIR") or "nautobot").strip("/")

    def _remote_topology_path(self, site):
        """
        Path to the topology file on the remote host:
        ~/{CONTAINERLAB_REMOTE_TOPOLOGY_DIR}/{site.name}/{site.name}.clab.yaml
        (one subfolder per site).
        """
        subdir = self._remote_topology_subdir()
        return f"~/{subdir}/{site.name}/{site.name}.clab.yaml"

    def _ensure_remote_topology_dir(self, site):
        """Create the remote topology directory for this site (e.g. ~/nautobot/Test)."""
        subdir = self._remote_topology_subdir()
        self._run_remote(f"mkdir -p ~/{subdir}/{site.name}")

    def _upload_topology(self, site, yaml_content: str):
        """Upload topology YAML to the containerlab server via SFTP (path: ~/nautobot/{site.name}/{site.name}.clab.yaml)."""
        cfg = get_plugin_config()
        connect_timeout = int(cfg.get("CONTAINERLAB_SSH_CONNECT_TIMEOUT", 15))
        host, port, user, password, key_path = self.get_connection_params()
        subdir = self._remote_topology_subdir()
        site_dir = site.name
        remote_filename = f"{site.name}.clab.yaml"

        logger.info("Connecting to %s:%s for SFTP upload", host, port)
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        try:
            if key_path and os.path.exists(key_path):
                client.connect(
                    hostname=host, port=port, username=user, key_filename=key_path,
                    timeout=connect_timeout,
                )
            else:
                client.connect(
                    hostname=host, port=port, username=user, password=password,
                    timeout=connect_timeout,
                )
        except Exception as e:
            logger.error("SSH connect to %s:%s failed: %s", host, port, e)
            raise

        try:
            # Resolve remote home (SFTP does not expand ~)
            stdin, stdout, stderr = client.exec_command("echo $HOME", timeout=10)
            home = stdout.read().decode().strip() or f"/home/{user}"
            base = f"{home.rstrip('/')}/{subdir}"
            site_path = f"{base}/{site_dir}"
            remote_path = f"{site_path}/{remote_filename}"

            sftp = client.open_sftp()
            for path in (base, site_path):
                try:
                    sftp.mkdir(path)
                except (IOError, OSError):
                    pass  # dir may already exist
            with sftp.file(remote_path, "w") as f:
                f.write(yaml_content)
            sftp.close()
            logger.info("Uploaded topology to %s", remote_path)
        finally:
            client.close()

    def _write_remote_site_file(self, site, filename, content):
        """Write a file under the site's remote directory (e.g. ~/nautobot/SiteName/filename)."""
        cfg = get_plugin_config()
        connect_timeout = int(cfg.get("CONTAINERLAB_SSH_CONNECT_TIMEOUT", 15))
        host, port, user, password, key_path = self.get_connection_params()
        subdir = self._remote_topology_subdir()
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        try:
            if key_path and os.path.exists(key_path):
                client.connect(hostname=host, port=port, username=user, key_filename=key_path, timeout=connect_timeout)
            else:
                client.connect(hostname=host, port=port, username=user, password=password, timeout=connect_timeout)
            stdin, stdout, stderr = client.exec_command("echo $HOME", timeout=10)
            home = stdout.read().decode().strip() or f"/home/{user}"
            base = f"{home.rstrip('/')}/{subdir}/{site.name}"
            remote_path = f"{base}/{filename}"
            sftp = client.open_sftp()
            try:
                sftp.mkdir(base)
            except (IOError, OSError):
                pass
            with sftp.file(remote_path, "w") as f:
                f.write(content)
            sftp.close()
        finally:
            client.close()

    def _upload_intended_configs_for_topology(self, site, job, log):
        """
        Get intended configs from Golden Config, upload them to the containerlab server
        in the site directory, and return device_startup_configs dict for the topology builder.
        Config files are placed next to the topology file so startup-config can use relative paths.
        """
        from nautobot_digital_twin.golden_config_intended import get_device_intended_config

        devices = list(Device.objects.filter(location=site).order_by("name"))
        device_startup_configs = {}
        for device in devices:
            config_content = get_device_intended_config(device)
            if not config_content:
                log("No intended config for %s; node will boot without startup-config.", device.name)
                continue
            filename = f"{device.name}.cfg"
            try:
                self._write_remote_site_file(site, filename, config_content)
                device_startup_configs[device.name] = filename
                log("Uploaded intended config for %s as %s (will use startup-config in topology).", device.name, filename)
            except Exception as e:
                logger.warning("Failed to upload intended config for %s: %s", device.name, e)
        return device_startup_configs

    def _check_images_exist_on_server(self, images, log_fn=None):
        """
        Verify that each image in `images` exists on the containerlab server (docker image inspect).
        Returns (True, []) if all present, (False, [missing_list]) if any are missing.
        """
        if not images:
            return True, []
        missing = []
        for image in sorted(images):
            exit_status, out, err = self._run_remote(f"docker image inspect --format '{{{{.Id}}}}' '{image}'")
            if exit_status != 0:
                missing.append(image)
            if log_fn and exit_status != 0:
                log_fn("Image not found on containerlab server: %s", image)
        return (len(missing) == 0), missing

    def deploy_site(self, site, job=None, config_source="empty_config"):
        """Deploy digital twin: generate topology, upload to server, run containerlab deploy.

        job= for UI logging. config_source: 'empty_config' or 'intended_config' (Golden Config).
        When intended_config: uploads configs to the site dir and sets startup-config in the topology
        so containerlab applies them on boot (see https://containerlab.dev/manual/nodes/#startup-config).
        """
        def log(msg, *args):
            if job:
                job.logger.info(msg, *args)
            logger.info(msg, *args)

        device_startup_configs = None
        if config_source == "intended_config":
            log("Ensuring remote topology directory and uploading intended configs...")
            self._ensure_remote_topology_dir(site)
            device_startup_configs = self._upload_intended_configs_for_topology(site, job, log)
            if not device_startup_configs:
                log("No intended configs found; deploying with empty config.")

        log("Generating topology from site devices and cables...")
        yaml_content = build_containerlab_yaml(site, device_startup_configs=device_startup_configs)
        log("Generated topology for %s (%s bytes)", site.name, len(yaml_content))

        # Pre-deploy check: required container images must exist on the containerlab server
        required_images = get_required_images_for_location(site)
        if required_images:
            log("Checking required container images on server: %s", ", ".join(sorted(required_images)))
            ok, missing = self._check_images_exist_on_server(required_images, log)
            if not ok:
                msg = "Missing container image(s) on containerlab server: %s. Pull them (e.g. docker pull <image>) or adjust CONTAINERLAB_PLATFORM_MAP." % ", ".join(missing)
                log(msg)
                return 1, "", msg

        # Optionally write to Nautobot local path (DIGITAL_TWIN_ROOT) for inspection
        cfg = get_plugin_config()
        local_root = cfg.get("DIGITAL_TWIN_ROOT", "").strip()
        if local_root and os.path.isdir(local_root):
            local_path = os.path.join(local_root, f"{site.name}.clab.yaml")
            try:
                with open(local_path, "w", encoding="utf-8") as f:
                    f.write(yaml_content)
                log("Wrote topology to %s", local_path)
            except OSError as e:
                logger.warning("Could not write local topology to %s: %s", local_path, e)

        # Upload to containerlab server and run deploy
        log("Ensuring remote topology directory for site exists...")
        self._ensure_remote_topology_dir(site)
        log("Uploading topology to containerlab server...")
        self._upload_topology(site, yaml_content)
        path = self._remote_topology_path(site)
        cmd = f"containerlab deploy -t {path} --reconfigure"
        log("Running containerlab deploy (command timeout from config)...")
        return self._run_remote(cmd)

    def destroy_site(self, site):
        path = self._remote_topology_path(site)
        cmd = f"containerlab destroy -t {path}"
        return self._run_remote(cmd)