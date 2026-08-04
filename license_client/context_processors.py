from license_client.state import resolve


def license_state(request):
    """Expose ``license_state`` to every template.

    Optional. This package renders nothing inside a customer's interface, so nothing
    needs this by default. Install it only if you want to show your own notice while
    the subscription is degraded, and read ``license_state.is_degraded``.
    """
    state = getattr(request, "license_state", None) or resolve(
        request.get_host().split(":")[0]
    )
    return {"license_state": state}
