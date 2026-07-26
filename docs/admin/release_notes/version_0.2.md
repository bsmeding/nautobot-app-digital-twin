# Version 0.2

<!-- towncrier release notes start -->

## 0.2.0b1 (beta)

### Added

- **EVE-NG backend (beta MVP)** — set `BACKEND: "eve-ng"` and configure `EVE_NG_URL` / credentials to deploy and destroy labs via the EVE-NG REST API.
- Backend capability flags (`supports_intended_config`, `supports_connectivity_tests`) so jobs degrade cleanly when a backend lacks a feature.
- `get_configured_backend_name()` and a real multi-backend registry (`containerlab`, `eve-ng`).

### Changed

- Jobs now use the configured backend (and the deployment's recorded backend on destroy/redeploy/health) instead of hard-coding containerlab.
- Declared runtime dependencies `paramiko` and `requests` in `pyproject.toml`.

### Known limitations (EVE-NG)

- Intended-config push and mesh ping validation remain containerlab-only for this beta.
- Nodes start Unconfigured; templates/images must already exist on the EVE-NG server (`EVE_NG_PLATFORM_MAP`).
