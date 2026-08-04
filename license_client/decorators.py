from functools import wraps

from django.http import HttpResponse


def license_exempt(view):
    """Mark a view as reachable even while the instance is suspended.

    Works on a function view, on a class-based or DRF view class, and on the result of
    ``as_view()``. Applied to a class it marks the class and hands it straight back,
    so ``as_view()`` still exists; wrapping the class in a function would break the
    URLconf at import time.

    With DRF's ``@api_view`` this must be the outermost decorator. ``api_view`` builds
    a fresh view class and carries none of the wrapped function's attributes across, so
    a marker underneath it is silently lost::

        @license_exempt      # outermost, or the exemption disappears
        @api_view(["GET"])
        def healthcheck(request):
            ...

    ``LICENSE_EXEMPT_URL_NAMES`` avoids the ordering question entirely and is the
    safer choice for a DRF codebase.

    Use sparingly: login, logout, health checks, and the data export route. Anything
    else marked exempt is a hole in your enforcement.
    """
    if isinstance(view, type):
        view.license_exempt = True
        return view

    view.license_exempt = True

    @wraps(view)
    def wrapper(*args, **kwargs):
        return view(*args, **kwargs)

    wrapper.license_exempt = True
    # as_view() results carry `cls` (DRF) or `view_class` (Django); preserve them so
    # the middleware can still identify the underlying class through this wrapper.
    for attr in ("cls", "view_class"):
        if hasattr(view, attr):
            setattr(wrapper, attr, getattr(view, attr))
    return wrapper


def requires_feature(feature: str):
    """Gate a plan-specific feature. Returns 402 when the client's plan does not include it."""

    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            state = getattr(request, "license_state", None)
            if state is None or feature not in (
                state.license.features if state.license else []
            ):
                # 402, matching what the middleware returns when it blocks. Built by
                # hand rather than with HttpResponsePaymentRequired, which only exists
                # on Django 5.1 and later — this package supports 4.2.
                return HttpResponse(
                    "This feature is not part of your plan.", status=402
                )
            return view_func(request, *args, **kwargs)

        return wrapper

    return decorator
