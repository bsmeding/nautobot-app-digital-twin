# Nautobot Digital Twin

<!--
Developer Note - Remove Me!

The README will have certain links/images broken until the PR is merged into `develop`. Update the GitHub links with whichever branch you're using (main etc.) if different.

The logo of the project is a placeholder (docs/images/icon-nautobot-digital-twin.png) - please replace it with your app icon, making sure it's at least 200x200px and has a transparent background!

To avoid extra work and temporary links, make sure that publishing docs (or merging a PR) is done at the same time as setting up the docs site on RTD, then test everything.
-->

<p align="center">
  <img src="https://raw.githubusercontent.com/bsmeding/nautobot-app-nautobot-digital-twin/develop/docs/images/icon-nautobot-digital-twin.png" class="logo" height="200px">
  <br>
  <a href="https://github.com/bsmeding/nautobot-app-nautobot-digital-twin/actions"><img src="https://github.com/bsmeding/nautobot-app-nautobot-digital-twin/actions/workflows/ci.yml/badge.svg?branch=main"></a>
  <a href="https://netdevops.it/projects/nautobot-digital-twin//"><img src="https://readthedocs.org/projects/nautobot-app-nautobot-digital-twin/badge/"></a>
  <a href="https://pypi.org/project/nautobot-digital-twin/"><img src="https://img.shields.io/pypi/v/nautobot-digital-twin"></a>
  <a href="https://pypi.org/project/nautobot-digital-twin/"><img src="https://img.shields.io/pypi/dm/nautobot-digital-twin"></a>
  <br>
  An <a href="https://networktocode.com/nautobot-apps/">App</a> for <a href="https://nautobot.com/">Nautobot</a>.
</p>

## Overview

> Developer Note: Add a long (2-3 paragraphs) description of what the App does, what problems it solves, what functionality it adds to Nautobot, what external systems it works with etc.

### Screenshots

> Developer Note: Add any representative screenshots of the App in action. These images should also be added to the `docs/user/app_use_cases.md` section.

> Developer Note: Place the files in the `docs/images/` folder and link them using only full URLs from GitHub, for example: `![Overview](https://raw.githubusercontent.com/bsmeding/nautobot-app-nautobot-digital-twin/develop/docs/images/app-overview.png)`. This absolute static linking is required to ensure the README renders properly in GitHub, the docs site, and any other external sites like PyPI.

More screenshots can be found in the [Using the App](https://netdevops.it/projects/nautobot-digital-twin//user/app_use_cases/) page in the documentation. Here's a quick overview of some of the app's added functionality:

![](https://raw.githubusercontent.com/bsmeding/nautobot-app-nautobot-digital-twin/develop/docs/images/placeholder.png)

## Installation (development with Docker)

When developing with the app mounted into a Nautobot Docker Compose stack:

1. Add the app to `PLUGINS` and `PLUGINS_CONFIG` in your `nautobot_config.py`.
2. Mount the app directory into **all** containers that load the plugin (nautobot, celery-worker, celery-beat).
3. **Install the app in each container** so the job code is loadable:

   ```bash
   docker compose exec nautobot bash -c "cd /opt/nautobot/nautobot-app-nautobot-digital-twin && pip install -e ."
   docker compose exec celery-worker-1 bash -c "cd /opt/nautobot/nautobot-app-nautobot-digital-twin && pip install -e ."
   docker compose exec celery-beat bash -c "cd /opt/nautobot/nautobot-app-nautobot-digital-twin && pip install -e ."
   ```

   Without this, jobs appear in the UI but fail with *"Job code for this job is not currently installed or loadable"* when run (the worker cannot import the job class).
4. Run `nautobot-server post_upgrade` and enable the job(s) in **Jobs → Jobs**, then restart services.

## Configuration

Configure the app in `nautobot_config.py` under `PLUGINS_CONFIG["nautobot_digital_twin"]`:

| Variable | Default | Description |
|----------|---------|-------------|
| `BACKEND` | `"containerlab"` | Backend to use for deployments. |
| `BACKEND_URLS` | `{}` | Optional backend-specific URLs. |
| `LOCATION_TYPE_NAME` | `"Site"` | Location type that shows the Digital Twin Start/Stop button (e.g. Site). |
| `USE_STRICT_SOFTWARE_VERSION` | `True` | Use exact Nautobot software_version for container images (e.g. `ceos:4.34.2F`). When `False`, use default/latest tag. |
| `CONTAINERLAB_SSH_HOST` | `"172.16.6.128"` | Hostname or IP of the containerlab server. |
| `CONTAINERLAB_SSH_PORT` | `22` | SSH port for the containerlab server. |
| `CONTAINERLAB_SSH_USER` | `"clab"` | SSH username (ignored when `CONTAINERLAB_SSH_CREDENTIALS_SECRETS_GROUP` is set). |
| `CONTAINERLAB_SSH_PASSWORD` | `"clab"` | SSH password (ignored when `CONTAINERLAB_SSH_CREDENTIALS_SECRETS_GROUP` is set). |
| `CONTAINERLAB_SSH_CREDENTIALS_SECRETS_GROUP` | `""` | Optional Nautobot Secrets Group name for SSH credentials (access type **SSH**, secret types Username/Password). When set, overrides `CONTAINERLAB_SSH_USER` and `CONTAINERLAB_SSH_PASSWORD`. |
| `CONTAINERLAB_SSH_KEY_PATH` | `""` | Optional path to SSH private key file (used instead of password when set). |
| `CONTAINERLAB_SSH_CONNECT_TIMEOUT` | `15` | SSH connection timeout in seconds. |
| `CONTAINERLAB_COMMAND_TIMEOUT_MINUTES` | `5` | Timeout in minutes for remote containerlab commands. |
| `CONTAINERLAB_REMOTE_TOPOLOGY_DIR` | `"nautobot"` | Subfolder under the SSH user's home for topology files (e.g. `~/nautobot/SiteName/`). |
| `CONTAINERLAB_PLATFORM_MAP` | `{}` | Map Nautobot platform (lowercase) to containerlab image, e.g. `{"arista_eos": "ceos", "cisco_ios": "ios"}`. |
| `DIGITAL_TWIN_ROOT` | `"/opt/nautobot/digital_twin"` | Local path on Nautobot where topology YAML files are written (for inspection). |
| `DIGITAL_TWIN_JOB_TIMEOUT_MINUTES` | `10` | Job timeout in minutes. |
| `DIGITAL_TWIN_AUTO_DESTROY_MINUTES` | `1440` | Auto-destroy deployments after this many minutes (0 = disable). Default 24h. |
| `DIGITAL_TWIN_FALLBACK_AUTH_SECRETS_GROUP` | `""` | Optional Nautobot Secrets Group for digital twin fallback auth (access type **Generic**, Username/Password). Used when appending platform-specific fallback auth to intended configs. |
| `REMOVE_CONFIG_LINES` | `[]` | Patterns to remove from intended config before deploy. When a line contains a pattern, that line and all indented children are removed. E.g. `["GigabitEthernet0/0", "radius-server"]` removes management interface and RADIUS blocks. |
| `DELETE_CONFIG_AFTER_DESTROY` | `True` | When `True`, remove the site folder (topology + config files) from the containerlab server when the digital twin is destroyed. |

## Try it out!

> Developer Note: Only keep this section if appropriate. Update link to correct sandbox.

This App is installed in the Nautobot Community Sandbox found over at [demo.nautobot.com](https://demo.nautobot.com/)!

> For a full list of all the available always-on sandbox environments, head over to the main page on [networktocode.com](https://www.networktocode.com/nautobot/sandbox-environments/).

## Documentation

Full documentation for this App can be found over on the [Nautobot Docs](https://netdevops.it) website:

- [User Guide](https://netdevops.it/projects/nautobot-digital-twin//user/app_overview/) - Overview, Using the App, Getting Started.
- [Administrator Guide](https://netdevops.it/projects/nautobot-digital-twin//admin/install/) - How to Install, Configure, Upgrade, or Uninstall the App.
- [Developer Guide](https://netdevops.it/projects/nautobot-digital-twin//dev/contributing/) - Extending the App, Code Reference, Contribution Guide.
- [Release Notes / Changelog](https://netdevops.it/projects/nautobot-digital-twin//admin/release_notes/).
- [Frequently Asked Questions](https://netdevops.it/projects/nautobot-digital-twin//user/faq/).


## Running deployments
See running deployemnts under Apps -> Nautobot Digital Twin -> Digital Twin Deployements
Here you can see the deployed digital twins, and who started a site. Also possible to end a digital twin (only the owner or a superuser)


### Contributing to the Documentation

You can find all the Markdown source for the App documentation under the [`docs`](https://github.com/bsmeding/nautobot-app-nautobot-digital-twin/tree/develop/docs) folder in this repository. For simple edits, a Markdown capable editor is sufficient: clone the repository and edit away.

If you need to view the fully-generated documentation site, you can build it with [MkDocs](https://www.mkdocs.org/). A container hosting the documentation can be started using the `invoke` commands (details in the [Development Environment Guide](https://netdevops.it/projects/nautobot-digital-twin//dev/dev_environment/#docker-development-environment)) on [http://localhost:8001](http://localhost:8001). Using this container, as your changes to the documentation are saved, they will be automatically rebuilt and any pages currently being viewed will be reloaded in your browser.

Any PRs with fixes or improvements are very welcome!

## Questions

For any questions or comments, please check the [FAQ](https://netdevops.it/projects/nautobot-digital-twin//user/faq/) first. Feel free to also swing by the [Network to Code Slack](https://networktocode.slack.com/) (channel `#nautobot`), sign up [here](http://slack.networktocode.com/) if you don't have an account.
