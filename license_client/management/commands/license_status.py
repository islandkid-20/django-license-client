from django.conf import settings
from django.core.management.base import BaseCommand

from license_client.state import resolve


class Command(BaseCommand):
    help = "Print the current licence state. Safe to run on a client's server."

    def handle(self, *args, **options):
        state = resolve(settings.LICENSE_DOMAIN)
        self.stdout.write(f"level:  {state.level}")
        self.stdout.write(f"reason: {state.reason}")
        if state.license:
            self.stdout.write(f"paid through: {state.license.period_end:%d %b %Y}")
            self.stdout.write(f"token expires: {state.license.expires_at}")
