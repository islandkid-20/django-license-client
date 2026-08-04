"""The body of a refusal, in one place.

The middleware and the optional DRF permission classes both answer the same question
and must answer it identically. Building the payload here is what stops the two paths
drifting into two different contracts for the same event.

The key is ``message``, not DRF's ``detail``. That is a deliberate choice: this is the
product's own API surface, and one shape for every licence refusal is worth more than
matching a framework default.
"""

READ_ONLY_CODE = "license_read_only"
SUSPENDED_CODE = "license_suspended"

READ_ONLY_MESSAGE = (
    "This system is in read-only mode while the subscription is settled. "
    "Your records are intact and can still be viewed and exported."
)
SUSPENDED_MESSAGE = (
    "Service suspended. Contact support to receive your invoice and restore access."
)


def refusal(state, *, read_only: bool) -> dict:
    """Machine-readable description of why a request was refused.

    ``support`` is carried so an API consumer can render a useful screen without a
    second call, which matters most when the API is the only thing a mobile client
    can reach.
    """
    license = state.license
    payload = {
        "message": READ_ONLY_MESSAGE if read_only else SUSPENDED_MESSAGE,
        "code": READ_ONLY_CODE if read_only else SUSPENDED_CODE,
        "level": state.level,
        "period_end": license.period_end.isoformat() if license else None,
        "support": state.support,
    }
    # The optional line an operator sets on the subscription, shown to the client.
    if license is not None and license.message:
        payload["notice"] = license.message
    return payload
