"""Enforcement. The only place in the client package that can deny a request."""

import logging

from django.http import JsonResponse
from django.shortcuts import render
from django.urls import Resolver404
from django.urls import resolve as resolve_url

from license_client.conf import get_config
from license_client.payloads import refusal
from license_client.state import resolve

logger = logging.getLogger(__name__)


class LicenseEnforcementMiddleware:
    """Blocks writes in read-only mode and everything in suspended mode.

    Ordering matters: place this **after** AuthenticationMiddleware so exempt views can
    still check permissions, and after SessionMiddleware so a client can log in to see
    the suspension notice rather than an anonymous wall.
    """

    def __init__(self, get_response):
        self.get_response = get_response
        # Called for its side effect only: a misconfigured product fails at startup
        # rather than on its first request. The result is deliberately not cached —
        # see _config.
        get_config()

    @property
    def _config(self):
        """Read the settings afresh each request.

        Caching this on the instance would be marginally faster and quietly wrong:
        Django builds the middleware chain once, so any product overriding a
        LICENSE_* setting in its own tests would find the override ignored with no
        error. Rebuilding a frozen dataclass costs nothing next to the request it
        guards.
        """
        return get_config()

    def __call__(self, request):
        config = self._config

        if self._is_exempt(request, config):
            return self.get_response(request)

        state = resolve(request.get_host().split(":")[0])

        if state.blocks_everything:
            return self._suspended_response(request, state, config)

        if state.blocks_writes and request.method in config.write_methods:
            return self._suspended_response(request, state, config, read_only=True)

        request.license_state = state
        return self.get_response(request)

    def _is_exempt(self, request, config) -> bool:
        path = request.path
        if any(path.startswith(prefix) for prefix in config.exempt_paths):
            return True
        try:
            match = resolve_url(path)
        except Resolver404:
            # An unroutable path is not exempt. Failing this way round means a URL we
            # cannot identify still gets enforced, never waved through.
            return False
        if match.url_name in config.exempt_url_names:
            return True
        return self._marked_exempt(match.func)

    @staticmethod
    def _marked_exempt(view) -> bool:
        """Is this view marked exempt, however it was written?

        ``as_view()`` returns a plain function that carries none of the class's own
        attributes, so a marker on a class-based view has to be read off the class.
        DRF hangs it on ``cls``; Django's own ``View`` uses ``view_class``. Checking
        the function alone silently under-reports, and an exemption that quietly
        fails is how a customer loses access to their data export.
        """
        if getattr(view, "license_exempt", False):
            return True
        view_class = getattr(view, "cls", None) or getattr(view, "view_class", None)
        return bool(
            view_class is not None and getattr(view_class, "license_exempt", False)
        )

    @staticmethod
    def _wants_json(request, config) -> bool:
        """Would this caller rather have JSON than a web page?

        A browser sends ``text/html,...,*/*;q=0.8`` and must get the notice page. Only
        an explicit request for JSON, or a JSON request body, or a path the product has
        declared as an API root, switches the format.
        """
        if any(request.path.startswith(prefix) for prefix in config.api_paths):
            return True
        if "application/json" in request.headers.get("Accept", ""):
            return True
        return "application/json" in (request.content_type or "")

    def _suspended_response(self, request, state, config, *, read_only: bool = False):
        if self._wants_json(request, config):
            # An API consumer calling response.json() on an HTML page gets a parse
            # error, and the customer sees a generic crash instead of the one message
            # this whole system exists to deliver.
            response = JsonResponse(refusal(state, read_only=read_only), status=402)
            response["Cache-Control"] = "no-store"
            return response

        context = {
            "state": state,
            "license": state.license,
            "support": state.support,
            "read_only": read_only,
            "expired_on": state.license.period_end if state.license else None,
        }
        template = (
            "license_client/read_only_blocked.html"
            if read_only
            else "license_client/suspended.html"
        )
        response = render(request, template, context, status=402)
        response["Cache-Control"] = "no-store"
        return response
