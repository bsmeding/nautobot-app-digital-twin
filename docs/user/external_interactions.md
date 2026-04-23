# External Interactions

This document describes external dependencies and prerequisites for this App to operate, including system requirements, API endpoints, interconnection or integrations to other applications or services, and similar topics.

This app orchestrates a **containerlab** host over SSH (topology deploy/destroy) and optional integrations such as Golden Config.

## External System Integrations

### From the App to Other Systems

### From Other Systems to the App

## Nautobot REST API endpoints

The app primarily operates through Nautobot Jobs and model interactions inside Nautobot. Standard Nautobot REST endpoints for related objects (Locations, Devices, Interfaces, Cables, Secrets) remain available for automation workflows.
