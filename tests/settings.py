"""Minimal Django settings for this package's own test run.

A product that installs license_client brings its own settings; these exist only so
the library can be exercised in isolation. LICENSE_CACHE_DIR is deliberately left
pointing at a path that does not exist — every test overrides it with a tmp_path, so
a test that forgets to isolate itself fails rather than reading a real token.
"""

SECRET_KEY = "test-only-not-a-real-key"
USE_TZ = True
TIME_ZONE = "Africa/Dar_es_Salaam"

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "license_client",
    "rest_framework",
]

MIDDLEWARE = [
    "license_client.middleware.LicenseEnforcementMiddleware",
]

DATABASES = {}

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "license_client.context_processors.license_state",
            ]
        },
    }
]

CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}

ROOT_URLCONF = "tests.urls"
ALLOWED_HOSTS = ["testserver", "client.example.com"]

# The runbook tells every product to exempt its record-export route, so the tests
# cover that path rather than only the decorator.
LICENSE_EXEMPT_URL_NAMES = ["data_export"]

# The four settings every product must define, plus the cache directory.
LICENSE_SERVER_URL = "https://licences.example.test"
LICENSE_INSTANCE_ID = "ins_000000000000000000000000"
LICENSE_INSTANCE_SECRET = "instance-secret-for-tests"
LICENSE_DOMAIN = "client.example.com"
LICENSE_CACHE_DIR = "/nonexistent/license-cache"
