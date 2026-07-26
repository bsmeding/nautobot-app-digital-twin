"""Shared cable helpers for topology builders."""

from django.contrib.contenttypes.models import ContentType
from nautobot.dcim.models import Cable, Interface


def iter_interface_cable_pairs(device_ids):
    """
    Yield (interface_a, interface_b) for cables between devices in device_ids.

    Both terminations must be Interfaces belonging to the given device id set.
    """
    if not device_ids:
        return
    interface_ct = ContentType.objects.get_for_model(Interface)
    interface_ids = list(Interface.objects.filter(device__id__in=device_ids).values_list("pk", flat=True))
    if not interface_ids:
        return
    for cable in Cable.objects.filter(
        termination_a_type=interface_ct,
        termination_a_id__in=interface_ids,
        termination_b_type=interface_ct,
        termination_b_id__in=interface_ids,
    ):
        a = getattr(cable, "termination_a", None)
        b = getattr(cable, "termination_b", None)
        if a is None or b is None or not isinstance(a, Interface) or not isinstance(b, Interface):
            continue
        if a.device_id not in device_ids or b.device_id not in device_ids:
            continue
        yield a, b
