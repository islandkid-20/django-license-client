"""The refresh task decides what may replace a working cached token.

Getting this wrong suspends a paying client, so every case here is about refusing to
overwrite a good token with a worse one.
"""

from datetime import timedelta

from django.utils import timezone

from license_client.conf import get_config
from license_client.tasks import refresh_license


def cached_token():
    config = get_config()
    return config.token_path.read_text() if config.token_path.exists() else None


def serve(monkeypatch, token):
    """Make the licence server return `token` (or None for an unreachable server)."""
    monkeypatch.setattr("license_client.tasks.fetch_token", lambda *a, **kw: token)


def test_unreachable_server_leaves_the_cached_token_alone(
    monkeypatch, license_token_factory
):
    """A network failure is an expected condition, not a reason to lose the licence."""
    good = license_token_factory()
    serve(monkeypatch, None)

    assert refresh_license() == "unreachable"
    assert cached_token() == good


def test_unverifiable_token_is_not_stored(monkeypatch, license_token_factory):
    good = license_token_factory()
    serve(monkeypatch, "not-a-jwt")

    assert refresh_license() == "invalid"
    assert cached_token() == good


def test_token_signed_for_another_instance_is_not_stored(
    monkeypatch, license_token_factory
):
    good = license_token_factory()
    serve(
        monkeypatch,
        license_token_factory(write=False, sign_with_other_instance_secret=True),
    )

    assert refresh_license() == "invalid"
    assert cached_token() == good


def test_expired_token_from_the_server_is_not_stored(
    monkeypatch, license_token_factory
):
    """verify() no longer rejects on expiry — is_stale does. This guard is what keeps
    a bug on the server side from replacing a working token with one that suspends
    the client on its next request."""
    good = license_token_factory()
    now = timezone.now()
    serve(
        monkeypatch,
        license_token_factory(
            write=False,
            issued_at=now - timedelta(days=5),
            token_exp=now - timedelta(days=2),
            period_end=now + timedelta(days=300),
        ),
    )

    assert refresh_license() == "stale"
    assert cached_token() == good


def test_a_healthy_token_replaces_the_cached_one(monkeypatch, license_token_factory):
    license_token_factory()
    fresh = license_token_factory(write=False)
    serve(monkeypatch, fresh)

    assert refresh_license() == "active"
    assert cached_token() == fresh
