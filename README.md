# Nautobot Digital Twin

An app for [Nautobot](https://nautobot.com/) that creates and manages disposable lab environments ("digital twins") from Nautobot source-of-truth data.

**Status:** `0.2.0b1` beta — ready for testing. Backends: **containerlab** (stable) and **EVE-NG** (beta MVP).

## What this app does

- Builds topology definitions from Nautobot `Location`, `Device`, `Interface`, and `Cable` data.
- Deploys and destroys labs using a selectable backend:
    - **containerlab** — SSH to a lab host (full feature set, including Golden Config push and ping tests)
    - **eve-ng** — EVE-NG Community/Pro REST API (deploy / destroy / health; intended-config push coming later)
- Supports Golden Config integration (containerlab):
    - deploy with intended config files,
    - push intended config to running labs,
    - execute "generate intended config" and push in one workflow.
- Adds Location Job Buttons for quick start/stop operations.

## Installation

Install from PyPI (or a beta wheel/sdist):

```bash
pip install nautobot-app-digital-twin==0.2.0b1
```

Enable it in `nautobot_config.py`:

### Containerlab

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

### EVE-NG

```python
PLUGINS = [
    "nautobot_digital_twin",
]

PLUGINS_CONFIG = {
    "nautobot_digital_twin": {
        "BACKEND": "eve-ng",
        "EVE_NG_URL": "https://eve.example.com",
        "EVE_NG_USER": "admin",
        "EVE_NG_PASSWORD": "eve",
        "EVE_NG_LAB_FOLDER": "/nautobot",
        "EVE_NG_VERIFY_SSL": False,
        # Optional: map Nautobot platforms to EVE templates/images installed on your server
        "EVE_NG_PLATFORM_MAP": {
            "arista_eos": {"template": "veos", "type": "qemu", "image": "veos-4.33.0F", "ethernet": 8},
            "cisco_ios": {"template": "vios", "type": "qemu", "image": "vios-adventerprisek9-m-15.9.3"},
        },
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

- `BACKEND`: `containerlab` or `eve-ng`
- `LOCATION_TYPE_NAME`: Location type where Start/Stop buttons are shown
- **Containerlab:** `CONTAINERLAB_SSH_*`, `CONTAINERLAB_PLATFORM_MAP`
- **EVE-NG:** `EVE_NG_URL`, `EVE_NG_USER`, `EVE_NG_PASSWORD`, `EVE_NG_LAB_FOLDER`, `EVE_NG_PLATFORM_MAP`, `EVE_NG_VERIFY_SSL`
- `REMOVE_CONFIG_LINES` / `REPLACE_CONFIG_PATTERNS` / `PLATFORM_ADD_CONFIG_LINES`: intended-config filtering pipeline
- `DIGITAL_TWIN_AUTO_DESTROY_MINUTES`: automatic cleanup timer

See the full docs for all available options.

## EVE-NG beta notes

- Deploy creates (or replaces) a lab under `EVE_NG_LAB_FOLDER`, adds one node per device, wires cables as hidden bridge networks, then starts all nodes.
- Templates/images must already exist on the EVE-NG server; configure `EVE_NG_PLATFORM_MAP` to match your inventory (`GET /api/list/templates/`).
- Intended-config push and mesh ping validation are not implemented for EVE-NG yet (containerlab only).
- Interface name matching is best-effort (exact/normalized match, then first free ethernet port).

## Documentation

- User Guide: [User Guide](https://netdevops.it/projects/nautobot-app-digital-twin/user-guide/)
- Admin Guide: [Admin Guide](https://netdevops.it/projects/nautobot-app-digital-twin/admin-guide/)
- Developer Guide: [Developer Guide](https://netdevops.it/projects/nautobot-app-digital-twin/developer-guide/)
- Release Notes: [Release Notes](https://netdevops.it/projects/nautobot-app-digital-twin/release-notes/)

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
