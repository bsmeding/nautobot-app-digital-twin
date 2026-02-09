"""Menu items."""

from nautobot.apps.ui import NavMenuAddButton, NavMenuGroup, NavMenuItem, NavMenuTab

items = (
    NavMenuItem(
        link="plugins:nautobot_digital_twin:digitaltwindeployment_list",
        name="Digital Twin Deployments",
        permissions=["nautobot_digital_twin.view_digitaltwindeployment"],
        buttons=(
            NavMenuAddButton(
                link="plugins:nautobot_digital_twin:digitaltwindeployment_add",
                permissions=["nautobot_digital_twin.add_digitaltwindeployment"],
            ),
        ),
    ),
)

menu_items = (
    NavMenuTab(
        name="Apps",
        groups=(NavMenuGroup(name="Nautobot Digital Twin", items=tuple(items)),),
    ),
)
