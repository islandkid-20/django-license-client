from functools import wraps

from django.http import HttpResponse


def license_exempt(view_func):
    """Mark a view as reachable even while the instance is suspended.

    Use sparingly: login, logout, health checks, and the data export route. Anything else
    marked exempt is a hole in your enforcement.
    """
    view_func.license_exempt = True

    @wraps(view_func)
    def wrapper(*args, **kwargs):
        return view_func(*args, **kwargs)

    wrapper.license_exempt = True
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
