"""Resolve the effective access level for this instance.

Two independent constraints apply and the stricter one always wins:

1. the billing dates inside the token
2. the token's own expiry, which is the offline tolerance window

That is what stops a client bypassing enforcement by blocking the licence server.
"""

import json
import logging
from dataclasses import dataclass
from pathlib import Path

from django.core.cache import cache
from django.utils import timezone

from license_client.conf import get_config
from license_client.tokens import License, TokenInvalid, verify

logger = logging.getLogger(__name__)

CACHE_KEY = "license_client:resolved"
CACHE_TTL = 60

ACTIVE = "active"
GRACE = "grace"
READ_ONLY = "read_only"
SUSPENDED = "suspended"


@dataclass(frozen=True)
class AccessState:
    level: str
    reason: str
    license: License | None = None

    @property
    def blocks_everything(self) -> bool:
        return self.level == SUSPENDED

    @property
    def blocks_writes(self) -> bool:
        return self.level in (READ_ONLY, SUSPENDED)

    @property
    def is_degraded(self) -> bool:
        """Past the paid period, but the product is still usable.

        This package renders nothing of its own in these states: injecting a notice
        into a customer's interface shows a billing problem to every cashier and
        driver who cannot act on it, while the people who can are reached by the
        licence server's SMS and email reminders instead.

        Exposed so a product can surface its own notice if it wants one.
        """
        return self.level in (GRACE, READ_ONLY)

    @property
    def support(self) -> dict:
        return self.license.support if self.license else {}


def _read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return {}


def store_token(raw_token: str) -> None:
    config = get_config()
    config.cache_dir.mkdir(parents=True, exist_ok=True)
    config.token_path.write_text(raw_token)
    cache.delete(CACHE_KEY)


def record_issued_at(issued_at: int) -> None:
    """Remember the newest token we have seen, to detect a clock rollback later."""
    config = get_config()
    state = _read_json(config.state_path)
    if issued_at > state.get("max_issued_at", 0):
        state["max_issued_at"] = issued_at
        config.state_path.write_text(json.dumps(state))


def resolve(domain: str) -> AccessState:
    """The single source of truth for the middleware. Cached briefly to stay cheap."""
    cached = cache.get(CACHE_KEY)
    if cached is not None:
        return cached

    state = _resolve_uncached(domain)
    cache.set(CACHE_KEY, state, CACHE_TTL)
    return state


def _resolve_uncached(domain: str) -> AccessState:
    config = get_config()

    if not config.token_path.exists():
        # Never licensed. A fresh install must be activated before it serves anything.
        return AccessState(SUSPENDED, "no_license")

    stored = _read_json(config.state_path)
    try:
        license = verify(
            config.token_path.read_text(),
            config,
            expected_domain=domain,
            min_issued_at=stored.get("max_issued_at", 0),
        )
    except TokenInvalid as exc:
        logger.error("licence token rejected: %s", exc)
        return AccessState(SUSPENDED, "invalid_license")

    if license.status == "revoked":
        return AccessState(SUSPENDED, "revoked", license)

    if license.is_stale:
        # Cannot reach the server and the tolerance window has closed.
        return AccessState(SUSPENDED, "unreachable", license)

    now = timezone.now()
    if now <= license.period_end:
        level = ACTIVE
    elif now <= license.grace_end:
        level = GRACE
    elif now <= license.read_only_end:
        level = READ_ONLY
    else:
        level = SUSPENDED

    # The server's own view can only ever be stricter, never more permissive.
    if license.status == SUSPENDED:
        level = SUSPENDED
    elif license.status == READ_ONLY and level in (ACTIVE, GRACE):
        level = READ_ONLY

    return AccessState(level, license.status, license)
