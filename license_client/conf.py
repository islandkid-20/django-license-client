"""Client configuration with safe defaults.

Every product sets four environment variables and nothing else. Defaults are chosen so
that a misconfigured instance fails loudly at startup rather than quietly running unlicensed.
"""

from dataclasses import dataclass, field
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured


@dataclass(frozen=True)
class LicenseSettings:
    server_url: str
    instance_id: str
    instance_secret: str
    cache_dir: Path
    request_timeout: int = 10
    clock_skew_tolerance: int = 300
    exempt_paths: tuple = field(default_factory=tuple)
    exempt_url_names: tuple = field(default_factory=tuple)
    write_methods: tuple = ("POST", "PUT", "PATCH", "DELETE")
    # Path prefixes that always answer JSON, for API clients that send no usable
    # Accept header. Content negotiation covers the well-behaved ones on its own.
    api_paths: tuple = field(default_factory=tuple)

    @property
    def heartbeat_url(self) -> str:
        return f"{self.server_url.rstrip('/')}/api/v1/licensing/heartbeat/"

    @property
    def token_path(self) -> Path:
        return self.cache_dir / "license.jwt"

    @property
    def state_path(self) -> Path:
        return self.cache_dir / "license.state.json"


DEFAULT_EXEMPT_PATHS = (
    "/__license__/",
    "/static/",
    "/media/",
    "/healthz",
    "/favicon.ico",
)


def get_config() -> LicenseSettings:
    try:
        server_url = settings.LICENSE_SERVER_URL
        instance_id = settings.LICENSE_INSTANCE_ID
        instance_secret = settings.LICENSE_INSTANCE_SECRET
    except AttributeError as exc:
        raise ImproperlyConfigured(
            "LICENSE_SERVER_URL, LICENSE_INSTANCE_ID and LICENSE_INSTANCE_SECRET are required."
        ) from exc

    return LicenseSettings(
        server_url=server_url,
        instance_id=instance_id,
        instance_secret=instance_secret,
        cache_dir=Path(getattr(settings, "LICENSE_CACHE_DIR", "/var/lib/license")),
        exempt_paths=DEFAULT_EXEMPT_PATHS
        + tuple(getattr(settings, "LICENSE_EXEMPT_PATHS", ())),
        exempt_url_names=tuple(getattr(settings, "LICENSE_EXEMPT_URL_NAMES", ())),
        api_paths=tuple(getattr(settings, "LICENSE_API_PATHS", ())),
    )
