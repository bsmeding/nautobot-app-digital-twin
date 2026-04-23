# Getting Started with the App

This document provides a step-by-step tutorial on how to get the App going and how to use it.

## Install the App

To install the App, please follow the instructions detailed in the [Installation Guide](../admin/install.md).

## First steps with the App

1. Confirm plugin installation and run `nautobot-server ensure_digital_twin_job_buttons`.
2. Open a Location that matches `LOCATION_TYPE_NAME`.
3. Launch the **Start Digital Twin** job/button for that Location.
4. Verify deployment status in **Apps -> Nautobot Digital Twin -> Digital Twin Deployments**.

## What are the next steps?

- Generate intended configs (if Golden Config is enabled) and push them to running twins.
- Tune config filtering (`REMOVE_CONFIG_LINES`, `REPLACE_CONFIG_PATTERNS`, `PLATFORM_ADD_CONFIG_LINES`) for lab-safe device bootstrap behavior.
- Configure auto-destroy policies for cleanup and resource control.

You can check out the [Use Cases](app_use_cases.md) section for more examples.
