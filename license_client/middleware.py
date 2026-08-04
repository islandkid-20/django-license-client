"""Enforcement. The only place in the client package that can deny a request."""

import logging

from django.shortcuts import render
from django.urls import Resolver404
from django.urls import resolve as resolve_url

from license_client.conf import get_config
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
        self.config = get_config()

    def __call__(self, request):
        if self._is_exempt(request):
            return self.get_response(request)

        state = resolve(request.get_host().split(":")[0])

        if state.blocks_everything:
            return self._suspended_response(request, state)

        if state.blocks_writes and request.method in self.config.write_methods:
            return self._suspended_response(request, state, read_only=True)

        request.license_state = state
        return self.get_response(request)

    def _is_exempt(self, request) -> bool:
        path = request.path
        if any(path.startswith(prefix) for prefix in self.config.exempt_paths):
            return True
        try:
            match = resolve_url(path)
        except Resolver404:
            # An unroutable path is not exempt. Failing this way round means a URL we
            # cannot identify still gets enforced, never waved through.
            return False
        if match.url_name in self.config.exempt_url_names:
            return True
        return getattr(match.func, "license_exempt", False)

    def _suspended_response(self, request, state, *, read_only: bool = False):
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
