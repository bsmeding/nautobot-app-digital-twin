# App Overview

This document provides an overview of the App including critical information and important considerations when applying it to your Nautobot environment.

!!! note
    Throughout this documentation, the terms "app" and "plugin" will be used interchangeably.

## Description

Nautobot Digital Twin lets operators instantiate lab environments directly from Nautobot data so topologies can be validated, tested, and iterated safely.

The app generates **containerlab** topology artifacts from Nautobot objects and orchestrates lab lifecycle operations (start/stop, config push, cleanup) through Nautobot jobs.

## Audience (User Personas) - Who should use this App?

- Network automation engineers building and validating topology-driven workflows.
- NetDevOps and platform teams validating intended configurations before production rollout.
- Lab and test engineers who need repeatable "from source of truth" ephemeral environments.

## Authors and Maintainers

The app is maintained in the `bsmeding/nautobot-app-digital-twin` repository. Use repository issues and pull requests for maintenance and contribution workflows.

## Nautobot Features Used

The app integrates with core Nautobot models (Locations, Devices, Interfaces, Cables), Jobs, and optional integrations such as Golden Config and Secrets.

### Extras

- Jobs are provided to create, update, and operate digital twin environments.
- Optional Job Buttons are available for Location objects to start and stop digital twins quickly.
