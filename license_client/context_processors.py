from license_client.state import resolve


def license_state(request):
    """Exposes ``license_state`` to every template so the banner renders itself."""
    state = getattr(request, "license_state", None) or resolve(
        request.get_host().split(":")[0]
    )
    return {"license_state": state}
