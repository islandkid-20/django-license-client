from django.apps import AppConfig
from django.core.checks import Error, register


class LicenseClientConfig(AppConfig):
    name = "license_client"
    verbose_name = "Licence client"

    def ready(self):
        register(check_configuration)


def check_configuration(app_configs, **kwargs):
    """Fail `manage.py check` on a misconfigured install, so a bad deploy never starts."""
    from django.conf import settings

    errors = []
    required = [
        "LICENSE_SERVER_URL",
        "LICENSE_INSTANCE_ID",
        "LICENSE_INSTANCE_SECRET",
        "LICENSE_DOMAIN",
    ]
    for name in required:
        if not getattr(settings, name, None):
            errors.append(Error(f"{name} is not set.", id="license_client.E001"))

    middleware = "license_client.middleware.LicenseEnforcementMiddleware"
    if middleware not in settings.MIDDLEWARE:
        errors.append(
            Error(
                "LicenseEnforcementMiddleware is not installed.",
                id="license_client.E002",
            )
        )
    return errors
