"""Verify a licence token. This module decides nothing about access — it only answers
'is this token genuine, current, and addressed to me?'

Signed with HS256 using a key derived from this instance's own secret. The secret never
leaves the container and is never sent over the wire in either protocol."""

import logging
from dataclasses import dataclass
from datetime import datetime

import jwt
from django.utils import timezone

from license_client.conf import LicenseSettings
from license_client.signing import derive_token_key

logger = logging.getLogger(__name__)


class TokenInvalid(Exception):
    """Raised for any token we will not act on. The caller falls back to the cached state."""


@dataclass(frozen=True)
class License:
    status: str
    product: str
    period_end: datetime
    grace_end: datetime
    read_only_end: datetime
    features: list
    seats: int | None
    support: dict
    message: str
    issued_at: int
    expires_at: int

    @property
    def is_stale(self) -> bool:
        """The offline tolerance window has passed — we can no longer vouch for this token."""
        return timezone.now().timestamp() > self.expires_at


def verify(
    raw_token: str,
    config: LicenseSettings,
    *,
    expected_domain: str,
    min_issued_at: int = 0,
) -> License:
    key = derive_token_key(config.instance_secret)

    try:
        claims = jwt.decode(
            raw_token,
            key,
            algorithms=["HS256"],
            audience=expected_domain,
            issuer="license-server",
            options={
                "require": ["exp", "iat", "sub", "aud", "iss"],
                # `exp` must be present, but it is not enforced here. Expiry is the
                # offline tolerance window, and the caller needs to tell a token
                # that simply aged out ("unreachable" — the licence server has been
                # unreachable for three days) from one that is forged or addressed
                # elsewhere ("invalid_license"). Both suspend, but only one of them
                # means you should go and look at the network. `License.is_stale`
                # owns that decision; letting PyJWT raise here made it dead code.
                "verify_exp": False,
            },
        )
    except jwt.PyJWTError as exc:
        raise TokenInvalid(f"Signature or claims rejected: {exc}") from exc

    if claims.get("sub") != config.instance_id:
        raise TokenInvalid("Token was issued for a different instance")

    # Rolling back the system clock must not resurrect an old token.
    if claims["iat"] + config.clock_skew_tolerance < min_issued_at:
        raise TokenInvalid("Token is older than one we have already seen")

    lic = claims.get("lic") or {}
    if lic.get("v") != 1:
        raise TokenInvalid(f"Unsupported contract version {lic.get('v')}")

    return License(
        status=lic["status"],
        product=lic.get("product", ""),
        period_end=datetime.fromisoformat(lic["period_end"]),
        grace_end=datetime.fromisoformat(lic["grace_end"]),
        read_only_end=datetime.fromisoformat(lic["read_only_end"]),
        features=lic.get("features", []),
        seats=lic.get("seats"),
        support=lic.get("support", {}),
        message=lic.get("message", ""),
        issued_at=claims["iat"],
        expires_at=claims["exp"],
    )
