"""A stand-in for a product's URLconf, exercising each way a view can be exempt."""

from django.http import HttpResponse
from django.template import RequestContext, Template
from django.urls import include, path

from license_client.decorators import license_exempt


def thing(request):
    """An ordinary product view. Reads pass, writes are what enforcement blocks."""
    return HttpResponse("thing")


@license_exempt
def health(request):
    return HttpResponse("healthy")


def data_export(request):
    """Exempt by URL name, the way the runbook tells you to expose record export."""
    return HttpResponse("export")


def banner(request):
    """Renders just the banner, so its visibility can be asserted directly."""
    template = Template('[{% include "license_client/banner.html" %}]')
    return HttpResponse(template.render(RequestContext(request)))


urlpatterns = [
    path("", include("license_client.urls")),
    path("thing/", thing, name="thing"),
    path("health/", health, name="health"),
    path("export/", data_export, name="data_export"),
    path("banner/", banner, name="banner"),
]
