"""What the middleware actually denies.

Every other test proves a token is judged correctly. These prove that judgement is
enforced — and, just as important, that the exemptions really do stay open, because a
client locked out of its own data export is a worse failure than one that underpays.
"""

from datetime import timedelta

import pytest
from django.utils import timezone

DOMAIN = "client.example.com"
HOST = {"host": DOMAIN}

# Offsets past period_end that land in each window, given the 7 + 7 day defaults.
GRACE = 3
READ_ONLY = 10
SUSPENDED = 20


def expired(days):
    return timezone.now() - timedelta(days=days)


@pytest.mark.parametrize("days_past_end", [-1, GRACE])
def test_reads_and_writes_pass_while_access_is_full(
    client, license_token_factory, days_past_end
):
    license_token_factory(period_end=expired(days_past_end))
    assert client.get("/thing/", headers=HOST).status_code == 200
    assert client.post("/thing/", headers=HOST).status_code == 200


def test_read_only_allows_reads_and_blocks_writes(client, license_token_factory):
    license_token_factory(period_end=expired(READ_ONLY))
    assert client.get("/thing/", headers=HOST).status_code == 200

    response = client.post("/thing/", headers=HOST)
    assert response.status_code == 402
    assert b"read-only" in response.content.lower()


def test_suspended_blocks_everything(client, license_token_factory):
    license_token_factory(period_end=expired(SUSPENDED))
    assert client.get("/thing/", headers=HOST).status_code == 402
    assert client.post("/thing/", headers=HOST).status_code == 402


def test_blocked_responses_are_never_cached(client, license_token_factory):
    """A cached suspension page would survive the payment that lifted it."""
    license_token_factory(period_end=expired(SUSPENDED))
    response = client.get("/thing/", headers=HOST)
    assert response["Cache-Control"] == "no-store"


def test_suspended_page_carries_support_contacts(client, license_token_factory):
    """This page is the only thing a locked-out client can see; it must say who to call."""
    license_token_factory(period_end=expired(SUSPENDED))
    body = client.get("/thing/", headers=HOST).content.decode()
    assert "+255700000000" in body
    assert "billing@example.test" in body


# -- exemptions ----------------------------------------------------------------


@pytest.mark.parametrize(
    "path,why",
    [
        ("/health/", "license_exempt decorator"),
        ("/export/", "LICENSE_EXEMPT_URL_NAMES"),
        ("/__license__/status", "DEFAULT_EXEMPT_PATHS prefix"),
    ],
)
def test_exempt_routes_stay_open_while_suspended(
    client, license_token_factory, path, why
):
    license_token_factory(period_end=expired(SUSPENDED))
    assert client.get(path, headers=HOST).status_code == 200, why


def test_an_unroutable_path_is_enforced_not_waved_through(
    client, license_token_factory
):
    """_is_exempt swallows Resolver404 and returns False.

    Failing that way round means a URL the middleware cannot identify is still
    enforced. If it returned True, any unmatched path would bypass licensing.
    """
    license_token_factory(period_end=expired(SUSPENDED))
    response = client.get("/no-such-route/", headers=HOST)
    assert response.status_code == 402


def test_no_token_at_all_blocks_the_product(client):
    """A fresh install must be activated before it serves anything."""
    assert client.get("/thing/", headers=HOST).status_code == 402


def test_a_token_for_another_domain_does_not_unlock_this_one(
    client, license_token_factory
):
    license_token_factory(audience="someone-else.example.com")
    assert client.get("/thing/", headers=HOST).status_code == 402


# -- banner --------------------------------------------------------------------


def test_banner_is_silent_while_healthy(client, license_token_factory):
    license_token_factory(period_end=expired(-1))
    # Asserting on markup, not exact bytes: the template's {% if %} leaves whitespace
    # behind either way, and that is not what "renders nothing" means here.
    assert b"<div" not in client.get("/banner/", headers=HOST).content


@pytest.mark.parametrize(
    "days_past_end,expected",
    [(GRACE, b"overdue"), (READ_ONLY, b"Read-only")],
)
def test_banner_warns_once_the_period_has_lapsed(
    client, license_token_factory, days_past_end, expected
):
    license_token_factory(period_end=expired(days_past_end))
    assert expected in client.get("/banner/", headers=HOST).content
