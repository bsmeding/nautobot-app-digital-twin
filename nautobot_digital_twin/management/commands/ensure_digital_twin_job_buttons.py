"""
Management command to create default Job Buttons for Location (Start/Stop Digital Twin).

Normally this is handled automatically via `nautobot_database_ready` (see `signals.py`),
but this command can be used to force creation if needed.

Run after Job records exist (i.e. after `nautobot-server post_upgrade`).
"""

from django.core.management.base import BaseCommand
from django.apps import apps

from nautobot_digital_twin.signals import create_default_job_buttons


class Command(BaseCommand):
    help = "Create default Job Buttons (Start/Stop Digital Twin on Location). Run after: nautobot-server post_upgrade"

    def handle(self, *args, **options):
        created, skipped = create_default_job_buttons(apps=apps)
        if created:
            self.stdout.write(self.style.SUCCESS("Created %s Job Button(s)." % created))
        if skipped:
            self.stdout.write(
                self.style.WARNING(
                    "Skipped %s button(s): Job records not in database. "
                    "Run: nautobot-server post_upgrade then run this command again."
                )
                % skipped
            )
        self.stdout.write(
            "Check Jobs → Job Buttons. Enable 'Start Digital Twin (Job Button)' and "
            "'Stop Digital Twin (Job Button)' under Jobs → Jobs if needed."
        )
