# Extending the App

This app is extensible through additional jobs, backend adapters, and configuration transformations.

## Adding a backend

1. Implement `DigitalTwinBackend` in `nautobot_digital_twin/backends/<name>.py` (`deploy_site` / `destroy_site` required; optional: `check_health`, `get_topology_status`, `push_intended_config`, `ping_from_node`).
2. Register it in `nautobot_digital_twin/backends/__init__.py` `_BACKENDS`.
3. Add default settings in `NautobotDigitalTwinConfig.default_settings`.
4. Document config keys in `README.md` / admin install docs.

Current backends: `containerlab`, `eve-ng`.

Extending the application is welcome, however it is best to open an issue first, to ensure that a PR would be accepted and makes sense in terms of features and design.
