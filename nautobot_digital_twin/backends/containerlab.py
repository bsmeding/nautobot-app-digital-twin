# nautobot_digital_twin/backends/containerlab.py
import logging
import os
import re
from contextlib import contextmanager

import paramiko

from nautobot.dcim.models import Device
from nautobot_digital_twin.plugin_config import get_plugin_config
from nautobot_digital_twin.secrets_utils import get_credentials_from_secrets_group
from nautobot_digital_twin.topology import build_containerlab_yaml, get_required_images_for_location

from .base import DigitalTwinBackend

logger = logging.getLogger(__name__)


def _get_ssh_access_type():
    """Return the SSH access type constant (handles Nautobot version differences)."""
    try:
        from nautobot.extras.choices import SecretsGroupAccessTypeChoices
        return getattr(SecretsGroupAccessTypeChoices, "TYPE_SSH", "ssh")
    except (ImportError, AttributeError):
        return "ssh"


class ContainerlabBackend(DigitalTwinBackend):
    """Containerlab backend; uses backend_url from app config BACKEND_URLS if set."""

    def get_connection_params(self):
        """Return (host, port, user, password, key_path) from plugin config or Secrets Group."""
        cfg = get_plugin_config()
        host = cfg["CONTAINERLAB_SSH_HOST"]
        port = cfg.get("CONTAINERLAB_SSH_PORT", 22)
        user = cfg.get("CONTAINERLAB_SSH_USER", "clab")
        password = cfg.get("CONTAINERLAB_SSH_PASSWORD", "clab")
        key_path = cfg.get("CONTAINERLAB_SSH_KEY_PATH", "")

        secrets_group = (cfg.get("CONTAINERLAB_SSH_CREDENTIALS_SECRETS_GROUP") or "").strip()
        if secrets_group:
            creds = get_credentials_from_secrets_group(secrets_group, _get_ssh_access_type())
            if creds:
                user, password = creds
                logger.debug("Using SSH credentials from Secrets Group '%s'", secrets_group)

        return host, port, user, password, key_path

    @contextmanager
    def _connect(self):
        """Context manager yielding a connected paramiko SSHClient. Closes on exit."""
        cfg = get_plugin_config()
        connect_timeout = int(cfg.get("CONTAINERLAB_SSH_CONNECT_TIMEOUT", 15))
        host, port, user, password, key_path = self.get_connection_params()
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        try:
            if key_path and os.path.exists(key_path):
                client.connect(
                    hostname=host, port=port, username=user,
                    key_filename=key_path, timeout=connect_timeout,
                )
            else:
                client.connect(
                    hostname=host, port=port, username=user,
                    password=password, timeout=connect_timeout,
                )
            logger.debug("SSH connected to %s:%s", host, port)
            yield client
        except Exception as e:
            logger.error("SSH connect to %s:%s failed: %s", host, port, e)
            raise
        finally:
            client.close()

    def _run_remote(self, command: str, timeout: int = None):
        """Run command over SSH. timeout: seconds to wait for command (from config if None)."""
        cfg = get_plugin_config()
        if timeout is None:
            timeout = int(cfg.get("CONTAINERLAB_COMMAND_TIMEOUT_MINUTES", 5)) * 60
        host, port, _, _, _ = self.get_connection_params()
        logger.info("Running remote command on %s:%s (timeout=%ss): %s", host, port, timeout, command)
        with self._connect() as client:
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

    def check_health(self):
        """Check if containerlab is installed on the remote host."""
        exit_status, out, err = self._run_remote("containerlab version")
        host, port, _, _, _ = self.get_connection_params()
        if exit_status != 0:
            return False, f"Containerlab is not installed on {host}: {err.strip() or out.strip()}"
        return True, f"Containerlab is installed on {host}"

    def _remote_topology_subdir(self):
        """Subdir under SSH user home for topology files (CONTAINERLAB_REMOTE_TOPOLOGY_DIR)."""
        cfg = get_plugin_config()
        return (cfg.get("CONTAINERLAB_REMOTE_TOPOLOGY_DIR") or "nautobot").strip("/")

    def _remote_topology_path(self, site):
        """Path to topology file: ~/{CONTAINERLAB_REMOTE_TOPOLOGY_DIR}/{site.name}/{site.name}.clab.yaml"""
        subdir = self._remote_topology_subdir()
        return f"~/{subdir}/{site.name}/{site.name}.clab.yaml"

    def _resolve_home(self, client):
        """Resolve the SSH user's home directory (SFTP does not expand ~)."""
        _, stdout, _ = client.exec_command("echo $HOME", timeout=10)
        home = stdout.read().decode().strip()
        if not home:
            _, user, _, _ = self.get_connection_params()[2], *self.get_connection_params()[2:]
            home = f"/home/{user}"
        return home

    def _ensure_remote_topology_dir(self, site):
        """Create the remote topology directory for this site."""
        subdir = self._remote_topology_subdir()
        self._run_remote(f"mkdir -p ~/{subdir}/{site.name}")

    def _upload_topology(self, site, yaml_content: str):
        """Upload topology YAML to the containerlab server via SFTP."""
        subdir = self._remote_topology_subdir()
        with self._connect() as client:
            _, stdout, _ = client.exec_command("echo $HOME", timeout=10)
            home = stdout.read().decode().strip() or f"/home/{self.get_connection_params()[2]}"
            base = f"{home.rstrip('/')}/{subdir}"
            site_path = f"{base}/{site.name}"
            remote_path = f"{site_path}/{site.name}.clab.yaml"
            sftp = client.open_sftp()
            for path in (base, site_path):
                try:
                    sftp.mkdir(path)
                except (IOError, OSError):
                    pass
            with sftp.file(remote_path, "w") as f:
                f.write(yaml_content)
            sftp.close()
            logger.info("Uploaded topology to %s", remote_path)

    def _write_remote_site_file(self, site, filename, content):
        """Write a file under the site's remote directory (e.g. ~/nautobot/SiteName/filename)."""
        subdir = self._remote_topology_subdir()
        with self._connect() as client:
            _, stdout, _ = client.exec_command("echo $HOME", timeout=10)
            home = stdout.read().decode().strip() or f"/home/{self.get_connection_params()[2]}"
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

    def _upload_intended_configs_for_topology(self, site, job, log):
        """
        Get intended configs from Golden Config, filter them, upload to the containerlab server,
        and return device_startup_configs dict for the topology builder.
        """
        from nautobot_digital_twin.golden_config_intended import get_device_intended_config
        from nautobot_digital_twin.config_filter import filter_config_remove_blocks

        cfg = get_plugin_config()
        remove_patterns = cfg.get("REMOVE_CONFIG_LINES") or []

        devices = list(Device.objects.filter(location=site).order_by("name"))
        device_startup_configs = {}
        for device in devices:
            config_content = get_device_intended_config(device)
            if not config_content:
                log("No intended config for %s; node will boot without startup-config.", device.name)
                continue
            if remove_patterns:
                config_content = filter_config_remove_blocks(config_content, remove_patterns)
                log("Filtered intended config for %s (REMOVE_CONFIG_LINES: %s)", device.name, remove_patterns)
            filename = f"{device.name}.cfg"
            try:
                self._write_remote_site_file(site, filename, config_content)
                device_startup_configs[device.name] = filename
                log("Uploaded intended config for %s as %s.", device.name, filename)
            except Exception as e:
                logger.warning("Failed to upload intended config for %s: %s", device.name, e)
        return device_startup_configs

    def _check_images_exist_on_server(self, images, log_fn=None):
        """
        Verify that each image exists on the containerlab server (docker image inspect).
        Returns (True, []) if all present, (False, [missing_list]) otherwise.
        """
        if not images:
            return True, []
        missing = []
        for image in sorted(images):
            exit_status, out, err = self._run_remote(f"docker image inspect --format '{{{{.Id}}}}' '{image}'")
            if exit_status != 0:
                missing.append(image)
                if log_fn:
                    log_fn("Image not found on containerlab server: %s", image)
        return (len(missing) == 0), missing

    def _pull_missing_images(self, images, log_fn=None):
        """
        Attempt to pull each image on the containerlab server via docker pull.
        Returns (True, []) if all succeeded, (False, [failed_list]) otherwise.
        """
        if not images:
            return True, []
        failed = []
        for image in sorted(images):
            if log_fn:
                log_fn("Pulling image %s...", image)
            exit_status, out, err = self._run_remote(f"docker pull '{image}'")
            if exit_status != 0:
                failed.append(image)
                if log_fn:
                    log_fn("Failed to pull %s: %s", image, err.strip() or out.strip() or "unknown error")
        return (len(failed) == 0), failed

    def get_topology_status(self, site):
        """Run containerlab inspect for the site topology. Returns (exit_status, out, err)."""
        path = self._remote_topology_path(site)
        return self._run_remote(f"containerlab inspect -t {path}")

    def _lab_name_for_site(self, site):
        """Return the containerlab lab name derived from site name (matches topology YAML)."""
        return re.sub(r"[^a-z0-9-]", "-", site.name.lower()).strip("-") or "lab"

    def _container_name(self, lab_name, device_name):
        """Return the Docker container name for a containerlab node."""
        return f"clab-{lab_name}-{device_name}"

    def ping_from_container(self, container_name, target_ip, count=3, timeout_sec=2):
        """
        Run ping from inside a running container via docker exec.
        Returns (exit_status, out, err). exit_status 0 = all packets received.
        """
        cmd = f"docker exec {container_name} ping -c {count} -W {timeout_sec} {target_ip}"
        return self._run_remote(cmd, timeout=30)

    def deploy_site(self, site, job=None, config_source="empty_config"):
        """Deploy digital twin: generate topology, upload to server, run containerlab deploy."""
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
                log("Attempting to pull missing image(s): %s", ", ".join(missing))
                pull_ok, pull_failed = self._pull_missing_images(missing, log)
                if not pull_ok:
                    msg = "Failed to pull image(s): %s. Check network access and image name, or adjust CONTAINERLAB_PLATFORM_MAP." % ", ".join(pull_failed)
                    log(msg)
                    return 1, "", msg
                ok, still_missing = self._check_images_exist_on_server(missing, log)
                if not ok:
                    msg = "Image(s) still missing after pull: %s. Adjust CONTAINERLAB_PLATFORM_MAP." % ", ".join(still_missing)
                    log(msg)
                    return 1, "", msg
                log("Successfully pulled missing image(s).")

        # Optionally write to Nautobot local path for inspection
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

        log("Ensuring remote topology directory for site exists...")
        self._ensure_remote_topology_dir(site)
        log("Uploading topology to containerlab server...")
        self._upload_topology(site, yaml_content)
        topo_dir = f"~/{self._remote_topology_subdir()}/{site.name}"
        topo_file = f"{site.name}.clab.yaml"
        cmd = f"cd {topo_dir} && containerlab deploy -t {topo_file} --reconfigure"
        log("Running containerlab deploy (command timeout from config)...")
        return self._run_remote(cmd)

    def destroy_site(self, site):
        path = self._remote_topology_path(site)
        exit_status, out, err = self._run_remote(f"containerlab destroy -t {path}")
        cfg = get_plugin_config()
        if cfg.get("DELETE_CONFIG_AFTER_DESTROY", True):
            site_dir = f"~/{self._remote_topology_subdir()}/{site.name}"
            rm_status, rm_out, rm_err = self._run_remote(f"rm -rf {site_dir}")
            if rm_status != 0:
                logger.warning("Could not remove site dir %s on backend: %s", site_dir, rm_err or rm_out)
        return exit_status, out, err
