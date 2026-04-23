# Nautobot Digital Twin

An app for [Nautobot](https://nautobot.com/) that creates and manages disposable lab environments ("digital twins") from Nautobot source-of-truth data.

## What this app does

- Builds topology definitions from Nautobot `Location`, `Device`, `Interface`, and `Cable` data.
- Deploys and destroys labs using **containerlab** (SSH to a lab host).
- Supports Golden Config integration:
    - deploy with intended config files,
    - push intended config to running labs,
    - execute "generate intended config" and push in one workflow.
- Adds Location Job Buttons for quick start/stop operations.

## Installation

Install from PyPI:

```bash
pip install nautobot-app-digital-twin
```

Enable it in `nautobot_config.py`:

```python
PLUGINS = [
    "nautobot_digital_twin",
]

PLUGINS_CONFIG = {
    "nautobot_digital_twin": {
        "BACKEND": "containerlab",
        "CONTAINERLAB_SSH_HOST": "172.16.6.128",
        "CONTAINERLAB_SSH_PORT": 22,
        "CONTAINERLAB_SSH_USER": "clab",
        "CONTAINERLAB_SSH_PASSWORD": "clab",
    }
}
```

Run post-upgrade and restart services:

```bash
nautobot-server post_upgrade
```

Optional: create/update Location job buttons:

```bash
nautobot-server ensure_digital_twin_job_buttons
```

## Key settings

Common `PLUGINS_CONFIG["nautobot_digital_twin"]` settings:

- `BACKEND`: must be `containerlab` (only supported backend)
- `LOCATION_TYPE_NAME`: Location type where Start/Stop buttons are shown
- `CONTAINERLAB_SSH_*`: credentials/host for remote containerlab server
- `CONTAINERLAB_PLATFORM_MAP`: map platform names to node kind/image
- `REMOVE_CONFIG_LINES` / `REPLACE_CONFIG_PATTERNS` / `PLATFORM_ADD_CONFIG_LINES`: intended-config filtering pipeline
- `DIGITAL_TWIN_AUTO_DESTROY_MINUTES`: automatic cleanup timer

See the full docs for all available options.

## Documentation

- User Guide: [User Guide](https://netdevops.it/projects/nautobot-digital-twin/user-guide/)
- Admin Guide: [Admin Guide](https://netdevops.it/projects/nautobot-digital-twin/admin-guide/)
- Developer Guide: [Developer Guide](https://netdevops.it/projects/nautobot-digital-twin/developer-guide/)
- Release Notes: [Release Notes](https://netdevops.it/projects/nautobot-digital-twin/release-notes/)

## Development

This repository includes:

- GitHub CI and release workflows (lint, test, docs build, PyPI publish).
- MkDocs configuration (`mkdocs.yml`) and Read the Docs config (`.readthedocs.yaml`).

Run docs locally:

```bash
poetry install --with docs
poetry run mkdocs serve
```

## Support

- Open an issue in this repository.
- For Nautobot community help, join [`#nautobot` on Network to Code Slack](https://slack.networktocode.com/).
