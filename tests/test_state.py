"""The tests that matter: the ones that prove enforcement cannot be bypassed."""

from datetime import timedelta

import pytest
from django.utils import timezone

from license_client.state import ACTIVE, GRACE, READ_ONLY, SUSPENDED, _resolve_uncached


@pytest.mark.parametrize(
    "days_past_end,expected",
    [(-1, ACTIVE), (3, GRACE), (10, READ_ONLY), (20, SUSPENDED)],
)
def test_windows_progress_in_order(license_token_factory, days_past_end, expected):
    license_token_factory(period_end=timezone.now() - timedelta(days=days_past_end))
    assert _resolve_uncached("client.example.com").level == expected


def test_expired_token_suspends_even_when_billing_looks_healthy(license_token_factory):
    """Blocking the licence server must not extend access indefinitely."""
    license_token_factory(
        period_end=timezone.now() + timedelta(days=300),
        token_exp=timezone.now() - timedelta(hours=1),
    )
    assert _resolve_uncached("client.example.com").reason == "unreachable"


def test_token_for_another_domain_is_rejected(license_token_factory):
    license_token_factory(audience="someone-else.example.com")
    assert _resolve_uncached("client.example.com").level == SUSPENDED


def test_token_signed_for_another_instance_is_rejected(license_token_factory):
    license_token_factory(sign_with_other_instance_secret=True)
    assert _resolve_uncached("client.example.com").reason == "invalid_license"


def test_clock_rollback_does_not_restore_an_old_token(
    license_token_factory, seen_issued_at
):
    seen_issued_at(timezone.now().timestamp())
    license_token_factory(issued_at=timezone.now() - timedelta(days=10))
    assert _resolve_uncached("client.example.com").reason == "invalid_license"


def test_missing_token_fails_closed():
    assert _resolve_uncached("client.example.com").level == SUSPENDED
