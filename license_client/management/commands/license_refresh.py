from django.core.management.base import BaseCommand

from license_client.tasks import refresh_license


class Command(BaseCommand):
    help = "Fetch a fresh licence token now. Run this once during deployment."

    def handle(self, *args, **options):
        result = refresh_license()
        self.stdout.write(self.style.SUCCESS(f"licence refresh: {result}"))
