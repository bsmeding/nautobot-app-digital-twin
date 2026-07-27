# Installing the App in Nautobot

Here you will find detailed instructions on how to **install** and **configure** the App within your Nautobot environment.

## Prerequisites

- The app is compatible with Nautobot 3.2.0 and higher.
- Database backend: PostgreSQL (standard Nautobot production backend).

!!! note
    Please check the [dedicated page](compatibility_matrix.md) for a full compatibility matrix and the deprecation policy.

### Access Requirements

- **containerlab backend:** SSH connectivity from Nautobot workers to your containerlab host.
- **eve-ng backend:** HTTPS (or HTTP) reachability from Nautobot workers to the EVE-NG API.
- Optional access to configured Git repositories when using Golden Config intended config workflows.

## Install Guide

!!! note
    Apps can be installed from the [Python Package Index](https://pypi.org/) or locally. See the [Nautobot documentation](https://docs.nautobot.com/projects/core/en/stable/user-guide/administration/installation/app-install/) for more details. The pip package name for this app is [`nautobot-app-digital-twin`](https://pypi.org/project/nautobot-app-digital-twin/).

The app is available as a Python package via PyPI and can be installed with `pip`:

```shell
pip install nautobot-app-digital-twin
```

To ensure Nautobot Digital Twin is automatically re-installed during future upgrades, create a file named `local_requirements.txt` (if not already existing) in the Nautobot root directory (alongside `requirements.txt`) and list the `nautobot-app-digital-twin` package:

```shell
echo nautobot-app-digital-twin >> local_requirements.txt
```

Once installed, the app needs to be enabled in your Nautobot configuration. The following block of code below shows the additional configuration required to be added to your `nautobot_config.py` file:

- Append `"nautobot_digital_twin"` to the `PLUGINS` list.
- Append the `"nautobot_digital_twin"` dictionary to the `PLUGINS_CONFIG` dictionary and override any defaults.

```python
# In your nautobot_config.py
PLUGINS = ["nautobot_digital_twin"]

# PLUGINS_CONFIG = {
#   "nautobot_digital_twin": {
#     ADD YOUR SETTINGS HERE
#   }
# }
```

Once the Nautobot configuration is updated, run the Post Upgrade command (`nautobot-server post_upgrade`) to run migrations and clear any cache:

```shell
nautobot-server post_upgrade
```

Then restart (if necessary) the Nautobot services which may include:

- Nautobot
- Nautobot Workers
- Nautobot Scheduler

```shell
sudo systemctl restart nautobot nautobot-worker nautobot-scheduler
```

### Job Buttons (Start/Stop Digital Twin on Location)

To have **Start Digital Twin** and **Stop Digital Twin** buttons appear on Location detail pages (and under **Jobs → Job Buttons**), run after `post_upgrade`:

```shell
nautobot-server ensure_digital_twin_job_buttons
```

Then open **Jobs → Job Buttons** to confirm; enable **Start Digital Twin (Job Button)** and **Stop Digital Twin (Job Button)** under **Jobs → Jobs** if they are not already enabled.

## App Configuration

Configure the app under `PLUGINS_CONFIG["nautobot_digital_twin"]` in `nautobot_config.py`.

Common settings:

- `BACKEND`: `containerlab` (default) or `eve-ng`.
- `LOCATION_TYPE_NAME`: Location type for Start/Stop Digital Twin job buttons.
- **Containerlab:** `CONTAINERLAB_SSH_HOST`, `CONTAINERLAB_SSH_PORT`, `CONTAINERLAB_SSH_USER`, `CONTAINERLAB_SSH_PASSWORD`, `CONTAINERLAB_SSH_CREDENTIALS_SECRETS_GROUP`, `CONTAINERLAB_PLATFORM_MAP`.
- **EVE-NG:** `EVE_NG_URL`, `EVE_NG_USER`, `EVE_NG_PASSWORD`, `EVE_NG_LAB_FOLDER`, `EVE_NG_PLATFORM_MAP`, `EVE_NG_VERIFY_SSL`, `EVE_NG_CREDENTIALS_SECRETS_GROUP`.
- `REMOVE_CONFIG_LINES`, `REPLACE_CONFIG_PATTERNS`, and `PLATFORM_ADD_CONFIG_LINES`: intended config transformation rules.
- `DIGITAL_TWIN_AUTO_DESTROY_MINUTES`: lab auto-destroy timeout.

For a complete and current list, see the project `README.md` and the in-code default settings in `nautobot_digital_twin/__init__.py`.
