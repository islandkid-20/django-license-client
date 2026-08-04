import logging

from celery import shared_task
from django.conf import settings

from license_client.conf import get_config
from license_client.state import record_issued_at, store_token
from license_client.tokens import TokenInvalid, verify
from license_client.transport import fetch_token

logger = logging.getLogger(__name__)


@shared_task(name="license_client.refresh")
def refresh_license() -> str:
    """Fetch and store a new token.

    Schedule this every hour. A token is valid for 72h, so the instance survives roughly
    three days of failed refreshes before it locks itself — long enough to cover a weekend
    outage, short enough that firewalling the licence server is not a workaround.
    """
    config = get_config()
    raw = fetch_token(config, app_version=getattr(settings, "APP_VERSION", ""))
    if raw is None:
        return "unreachable"

    try:
        license = verify(raw, config, expected_domain=settings.LICENSE_DOMAIN)
    except TokenInvalid as exc:
        logger.error("server returned a token we cannot verify: %s", exc)
        return "invalid"

    if license.is_stale:
        # verify() does not reject on expiry — is_stale owns that. Storing an
        # already-expired token would overwrite a good cached one and suspend a
        # paying client over what is a bug on the server side.
        logger.error("server returned an already-expired token; keeping the cached one")
        return "stale"

    store_token(raw)
    record_issued_at(license.issued_at)
    logger.info("licence refreshed, status=%s", license.status)
    return license.status
