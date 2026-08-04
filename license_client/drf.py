"""Optional Django REST Framework integration.

Import this module only from a product that has DRF installed. Nothing else in the
package imports it, so DRF stays an optional dependency.

**You usually do not need this.** ``LicenseEnforcementMiddleware`` already covers every
request, and with it installed these permissions are redundant for the ordinary case.
They earn their place in two situations:

- a route is exempt from the middleware but should still be licensed, and
- gating a plan feature, which the middleware knows nothing about.

Refusals here return 402 with the same body the middleware produces, built by
``license_client.payloads.refusal``, so an API consumer sees one shape whichever layer
turned the request away.
"""

from rest_framework.exceptions import APIException
from rest_framework.permissions import BasePermission

from license_client.conf import get_config
from license_client.payloads import refusal
from license_client.state import resolve


class LicenseRefused(APIException):
    """402 carrying the refusal payload verbatim.

    DRF's exception handler renders ``detail`` as-is when it is a dict, rather than
    wrapping it in ``{"detail": ...}``. That is what lets these responses use the same
    ``message`` key as the middleware without a product having to install a custom
    ``EXCEPTION_HANDLER``.
    """

    status_code = 402

    def __init__(self, payload: dict):
        super().__init__(detail=payload)


def _current_state(request):
    return resolve(request.get_host().split(":")[0])


class IsLicensed(BasePermission):
    """Refuse when the licence would refuse: everything suspended, writes read-only.

    ``permission_classes = [IsLicensed]``
    """

    def has_permission(self, request, view):
        state = _current_state(request)

        if state.blocks_everything:
            raise LicenseRefused(refusal(state, read_only=False))

        if state.blocks_writes and request.method in get_config().write_methods:
            raise LicenseRefused(refusal(state, read_only=True))

        return True


def HasLicenseFeature(feature: str):
    """Gate a view on a feature flag carried in the licence token.

    A factory rather than a class, because DRF instantiates every entry in
    ``permission_classes`` itself and so cannot take a pre-built instance::

        permission_classes = [IsLicensed, HasLicenseFeature("advanced_reports")]

    Absent or unreadable licence means absent feature. A plan is proof that a feature
    was paid for, so failing closed is the only safe direction.
    """

    class _HasLicenseFeature(BasePermission):
        def has_permission(self, request, view):
            state = _current_state(request)
            features = state.license.features if state.license else []
            if feature in features:
                return True

            payload = refusal(state, read_only=False)
            payload.update(
                {
                    "message": "This feature is not part of your plan.",
                    "code": "license_feature_unavailable",
                    "feature": feature,
                }
            )
            raise LicenseRefused(payload)

    _HasLicenseFeature.__name__ = f"HasLicenseFeature({feature!r})"
    _HasLicenseFeature.__qualname__ = _HasLicenseFeature.__name__
    return _HasLicenseFeature
