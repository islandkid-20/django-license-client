"""Signed HTTP call to the licence server. Deliberately the only outbound code path."""

import hashlib
import hmac
import json
import logging
import secrets
import socket
import time

import requests
from django import get_version as django_version

from license_client.conf import LicenseSettings

logger = logging.getLogger(__name__)


def _sign(secret: str, message: str) -> str:
    return hmac.new(secret.encode(), message.encode(), hashlib.sha256).hexdigest()


def fetch_token(config: LicenseSettings, *, app_version: str = "") -> str | None:
    """Return a fresh token, or ``None`` if the server could not be reached.

    Never raises. A network failure is an expected condition, not an error — the cached
    token keeps the client running until its tolerance window closes.
    """
    body = json.dumps(
        {
            "client_version": "1.0.0",
            "app_version": app_version,
            "hostname": socket.gethostname(),
            "metrics": {"django": django_version()},
        },
        separators=(",", ":"),
    ).encode()

    timestamp = str(int(time.time()))
    nonce = secrets.token_hex(16)
    body_hash = hashlib.sha256(body).hexdigest()
    signature = _sign(
        config.instance_secret,
        f"{config.instance_id}.{timestamp}.{nonce}.{body_hash}",
    )

    try:
        response = requests.post(
            config.heartbeat_url,
            data=body,
            headers={
                "Content-Type": "application/json",
                "X-Instance-Id": config.instance_id,
                "X-Timestamp": timestamp,
                "X-Nonce": nonce,
                "X-Signature": signature,
            },
            timeout=config.request_timeout,
        )
    except requests.RequestException as exc:
        logger.warning("licence heartbeat failed: %s", exc)
        return None

    if response.status_code == 200:
        return response.json().get("token")

    logger.warning(
        "licence heartbeat rejected (%s): %s", response.status_code, response.text[:200]
    )
    return None
