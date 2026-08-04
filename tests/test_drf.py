"""Enforcement seen from an API client.

A DRF product's callers are mobile apps, browser frontends and other services. Handing
one of them an HTML page means `response.json()` raises and the customer sees a generic
crash instead of the one message this system exists to deliver.
"""

from datetime import timedelta

import pytest
from django.utils import timezone

DOMAIN = "client.example.com"
JSON = {"host": DOMAIN, "accept": "application/json"}
BROWSER = {"host": DOMAIN, "accept": "text/html,application/xhtml+xml,*/*;q=0.8"}

GRACE = 3
READ_ONLY = 10
SUSPENDED = 20


def expired(days):
    return timezone.now() - timedelta(days=days)


# -- content negotiation --------------------------------------------------------


def test_suspended_api_request_gets_json_not_a_web_page(client, license_token_factory):
    license_token_factory(period_end=expired(SUSPENDED))
    response = client.get("/api/orders/", headers=JSON)

    assert response.status_code == 402
    assert response["Content-Type"].startswith("application/json")
    body = response.json()
    assert body["code"] == "license_suspended"
    assert body["level"] == "suspended"
    assert body["message"]


def test_read_only_write_from_an_api_client_gets_json(client, license_token_factory):
    license_token_factory(period_end=expired(READ_ONLY))
    response = client.post("/api/orders/", headers=JSON)

    assert response.status_code == 402
    body = response.json()
    assert body["code"] == "license_read_only"
    assert "exported" in body["message"]


def test_a_browser_still_gets_the_notice_page(client, license_token_factory):
    """Content negotiation must not take the human-readable page away."""
    license_token_factory(period_end=expired(SUSPENDED))
    response = client.get("/api/orders/", headers=BROWSER)

    assert response.status_code == 402
    assert response["Content-Type"].startswith("text/html")
    assert b"Service suspended" in response.content


def test_a_json_request_body_is_enough_to_infer_json(client, license_token_factory):
    """Clients that set Content-Type but forget Accept still get something parseable."""
    license_token_factory(period_end=expired(SUSPENDED))
    response = client.post(
        "/api/orders/",
        data="{}",
        content_type="application/json",
        headers={"host": DOMAIN},
    )

    assert response["Content-Type"].startswith("application/json")


def test_api_paths_setting_forces_json_without_an_accept_header(
    client, license_token_factory, settings
):
    license_token_factory(period_end=expired(SUSPENDED))
    assert client.get("/api/orders/", headers={"host": DOMAIN})[
        "Content-Type"
    ].startswith("text/html")

    settings.LICENSE_API_PATHS = ["/api/"]
    response = client.get("/api/orders/", headers={"host": DOMAIN})
    assert response["Content-Type"].startswith("application/json")


def test_the_refusal_carries_enough_to_render_a_screen(client, license_token_factory):
    """A mobile client should not need a second call to show something useful."""
    license_token_factory(
        period_end=expired(SUSPENDED), message="Invoice INV-0043 due."
    )
    body = client.get("/api/orders/", headers=JSON).json()

    assert body["support"]["phone"]
    assert body["support"]["email"]
    assert body["period_end"]
    assert body["notice"] == "Invoice INV-0043 due."


def test_refusals_are_never_cached(client, license_token_factory):
    license_token_factory(period_end=expired(SUSPENDED))
    assert client.get("/api/orders/", headers=JSON)["Cache-Control"] == "no-store"


# -- exemptions on class-based and DRF views ------------------------------------


@pytest.mark.parametrize(
    "path,how",
    [
        ("/api/export/", "license_exempt on the APIView class"),
        ("/api/health/", "license_exempt outermost over @api_view"),
    ],
)
def test_drf_exemptions_survive_as_view(client, license_token_factory, path, how):
    """as_view() carries none of a class's attributes, so this needs the class itself.

    An exemption that silently fails is how a customer loses access to their own data
    export during suspension.
    """
    license_token_factory(period_end=expired(SUSPENDED))
    response = client.get(path, headers=JSON)
    assert response.status_code == 200, how


# -- permission classes ---------------------------------------------------------


def test_is_licensed_refuses_when_suspended(client, license_token_factory):
    """The guarded route is middleware-exempt, so the permission class is the only guard."""
    license_token_factory(period_end=expired(SUSPENDED))
    response = client.get("/api/guarded/", headers=JSON)

    assert response.status_code == 402
    assert response.json()["code"] == "license_suspended"


def test_is_licensed_blocks_writes_but_not_reads_in_read_only(
    client, license_token_factory
):
    license_token_factory(period_end=expired(READ_ONLY))
    assert client.get("/api/guarded/", headers=JSON).status_code == 200

    response = client.post("/api/guarded/", headers=JSON)
    assert response.status_code == 402
    assert response.json()["code"] == "license_read_only"


def test_is_licensed_allows_everything_while_healthy(client, license_token_factory):
    license_token_factory(period_end=expired(-1))
    assert client.get("/api/guarded/", headers=JSON).status_code == 200
    assert client.post("/api/guarded/", headers=JSON).status_code == 201


def test_permission_refusal_uses_the_same_shape_as_the_middleware(
    client, license_token_factory
):
    """One contract for a licence refusal, whichever layer produced it."""
    license_token_factory(period_end=expired(SUSPENDED))
    from_middleware = client.get("/api/orders/", headers=JSON).json()
    from_permission = client.get("/api/guarded/", headers=JSON).json()

    assert from_middleware.keys() == from_permission.keys()
    assert from_middleware["code"] == from_permission["code"]
    assert "detail" not in from_permission


def test_feature_gate_allows_a_feature_the_plan_includes(client, license_token_factory):
    license_token_factory(period_end=expired(-1), features=["advanced_reports"])
    assert client.get("/api/reports/", headers=JSON).status_code == 200


def test_feature_gate_refuses_a_feature_the_plan_omits(client, license_token_factory):
    license_token_factory(period_end=expired(-1), features=["basic_reports"])
    response = client.get("/api/reports/", headers=JSON)

    assert response.status_code == 402
    body = response.json()
    assert body["code"] == "license_feature_unavailable"
    assert body["feature"] == "advanced_reports"


def test_feature_gate_fails_closed_without_a_licence(client):
    """No token means no proof the feature was paid for."""
    assert client.get("/api/reports/", headers=JSON).status_code == 402
