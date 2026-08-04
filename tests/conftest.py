"""Fixtures for the enforcement tests.

These tests are the reason this package can be trusted, so the fixtures mint tokens
the same way the licence server does — same claim names, same HS256 signature over a
key derived from the instance secret — rather than stubbing ``verify`` out. A fixture
that faked verification would let a real signature regression pass silently.

Keep the claim shape here in step with the licence server's token contract, which
is published at /api/schema/ on any running licence server. The contract document
itself lives in the server repository, which is not public.
"""

import json
import uuid
from datetime import timedelta

import jwt
import pytest
from django.core.cache import cache
from django.utils import timezone

from license_client.signing import derive_token_key

# Grace and read-only windows the server would have baked into the token. These match
# the Plan defaults (7 + 7), which is what the window-progression test assumes.
GRACE_DAYS = 7
READ_ONLY_DAYS = 7

OTHER_INSTANCE_SECRET = "a-different-deployments-secret"


@pytest.fixture(autouse=True)
def license_cache_dir(settings, tmp_path):
    """Point the licence cache at a fresh directory for every test.

    Autouse: a test that reads state without isolating it would otherwise pick up
    whatever the previous test wrote, and the failure would look like a logic bug.
    """
    settings.LICENSE_CACHE_DIR = str(tmp_path)
    cache.clear()
    yield tmp_path
    cache.clear()


@pytest.fixture
def license_token_factory(settings, license_cache_dir):
    """Write a signed licence token to the cache directory.

    Every argument has a working default, so a test names only the one property it is
    actually about. Returns the encoded token for tests that want to inspect it.
    """

    def _make(
        *,
        write=True,
        period_end=None,
        grace_end=None,
        read_only_end=None,
        token_exp=None,
        issued_at=None,
        audience=None,
        status="active",
        product="pos",
        features=None,
        seats=None,
        message="",
        contract_version=1,
        sign_with_other_instance_secret=False,
    ):
        now = timezone.now()
        issued_at = issued_at or now
        period_end = period_end if period_end is not None else now + timedelta(days=30)
        grace_end = grace_end or period_end + timedelta(days=GRACE_DAYS)
        read_only_end = read_only_end or grace_end + timedelta(days=READ_ONLY_DAYS)
        # The server's offline tolerance window: 72h from issue.
        token_exp = token_exp or issued_at + timedelta(hours=72)

        claims = {
            "iss": "license-server",
            "sub": settings.LICENSE_INSTANCE_ID,
            "aud": audience or settings.LICENSE_DOMAIN,
            "jti": str(uuid.uuid4()),
            "iat": int(issued_at.timestamp()),
            "nbf": int(issued_at.timestamp()),
            "exp": int(token_exp.timestamp()),
            "lic": {
                "v": contract_version,
                "product": product,
                "status": status,
                "period_end": period_end.isoformat(),
                "grace_end": grace_end.isoformat(),
                "read_only_end": read_only_end.isoformat(),
                "features": features if features is not None else [],
                "seats": seats,
                "support": {
                    "phone": "+255700000000",
                    "email": "billing@example.test",
                    "whatsapp": "+255700000000",
                },
                "message": message,
                "client": "Test Client",
            },
        }

        secret = (
            OTHER_INSTANCE_SECRET
            if sign_with_other_instance_secret
            else settings.LICENSE_INSTANCE_SECRET
        )
        token = jwt.encode(claims, derive_token_key(secret), algorithm="HS256")

        # write=False mints a token without installing it, for tests that need to
        # hand one to the refresh task and then assert it was *not* cached.
        if write:
            license_cache_dir.mkdir(parents=True, exist_ok=True)
            (license_cache_dir / "license.jwt").write_text(token)
            cache.clear()
        return token

    return _make


@pytest.fixture
def seen_issued_at(license_cache_dir):
    """Record the highest ``iat`` this instance claims to have already seen.

    This is the anti-rollback memory: a token older than this must be refused even
    though its signature is perfectly valid.
    """

    def _set(timestamp):
        license_cache_dir.mkdir(parents=True, exist_ok=True)
        (license_cache_dir / "license.state.json").write_text(
            json.dumps({"max_issued_at": int(timestamp)})
        )

    return _set
