"""A stand-in for a product's URLconf, exercising each way a view can be exempt."""

from django.http import HttpResponse
from django.template import RequestContext, Template
from django.urls import include, path
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework.views import APIView

from license_client.decorators import license_exempt
from license_client.drf import HasLicenseFeature, IsLicensed


def thing(request):
    """An ordinary product view. Reads pass, writes are what enforcement blocks."""
    return HttpResponse("thing")


@license_exempt
def health(request):
    return HttpResponse("healthy")


def data_export(request):
    """Exempt by URL name, the way the runbook tells you to expose record export."""
    return HttpResponse("export")


def page(request):
    """A rendered product page, for asserting that nothing is injected into it.

    The marker is what a real application's own markup stands in for: if anything
    from this package ever appears in a customer's interface, it shows up here.
    """
    template = Template("[{{ license_state.level|default:'' }}]")
    return HttpResponse(template.render(RequestContext(request)))


# -- a DRF product's endpoints -------------------------------------------------


class OrdersAPIView(APIView):
    def get(self, request):
        return Response({"orders": []})

    def post(self, request):
        return Response({"created": True}, status=201)


@license_exempt
class ApiExportAPIView(APIView):
    """Marked on the class, which as_view() does not carry across by itself."""

    def get(self, request):
        return Response({"records": []})


@license_exempt
@api_view(["GET"])
def api_health(request):
    """license_exempt must be outermost; api_view drops attributes underneath it."""
    return Response({"ok": True})


class GuardedAPIView(APIView):
    """Enforced by permission class rather than by the middleware."""

    permission_classes = [IsLicensed]

    def get(self, request):
        return Response({"ok": True})

    def post(self, request):
        return Response({"created": True}, status=201)


class ReportsAPIView(APIView):
    permission_classes = [HasLicenseFeature("advanced_reports")]

    def get(self, request):
        return Response({"report": []})


urlpatterns = [
    path("", include("license_client.urls")),
    path("thing/", thing, name="thing"),
    path("health/", health, name="health"),
    path("export/", data_export, name="data_export"),
    path("page/", page, name="page"),
    path("api/orders/", OrdersAPIView.as_view(), name="api_orders"),
    path("api/export/", ApiExportAPIView.as_view(), name="api_export"),
    path("api/health/", api_health, name="api_health"),
    # Exempt from the middleware, so the permission class is the only thing guarding
    # it. This is the case IsLicensed actually exists for.
    path("api/guarded/", license_exempt(GuardedAPIView.as_view()), name="api_guarded"),
    path("api/reports/", license_exempt(ReportsAPIView.as_view()), name="api_reports"),
]
