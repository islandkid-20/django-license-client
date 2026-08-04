# django-license-client

Subscription enforcement for Django applications that run on servers you do not
control.

You sell an application. It is installed on the customer's own hardware, or in their
own cloud account, and you have no shell access to it. When an invoice goes unpaid you
need the software to wind down — but not instantly, not silently, and never in a way
that holds the customer's own records hostage.

This package is the client half of that. It is installed inside your application. It
checks in with a licence server you run, caches a short-lived signed token, and
enforces the result locally on every request.

## How enforcement works

Each instance calls home on a schedule and receives a token signed with a key derived
from that deployment's own secret. The token is verified locally, in process, with no
network call in the request path. A licence-server outage therefore does not take your
customers down.

Access is withdrawn in stages rather than all at once:

| Window | Behaviour |
| --- | --- |
| Paid period | Full access |
| Grace, 7 days by default | Full access, warning banner |
| Read-only, 7 days by default | Reads and exports allowed, writes blocked |
| After that | Suspension notice with your support contacts |

Two independent limits apply and the stricter always wins: the billing dates carried
inside the token, and the token's own 72-hour expiry. The second is what makes
firewalling the licence server useless as a way around the first — once the cached
token ages out, the instance locks itself.

## Requirements

- Python 3.11 or later
- Django 4.2, 5.2 or 6.0
- A reachable licence server implementing the v1 token contract

Django 4.2 LTS through 6.0 are supported, including the current release. The test suite
runs against every combination below before a release:

| | Django 4.2 LTS | Django 5.2 LTS | Django 6.0 |
| --- | --- | --- | --- |
| Python 3.11 | yes | yes | — |
| Python 3.12 | yes | yes | yes |

Django 6.0 requires Python 3.12 or later, so the empty cell is Django's constraint
rather than this package's. Use Python 3.12 to run Django 6.0.

## Installation

```console
pip install django-license-client
```

The scheduled refresh is a Celery task. If your application uses Celery, install the
extra so the dependency is declared explicitly:

```console
pip install "django-license-client[celery]"
```

Without Celery you can still drive the refresh from cron, calling the management
command directly.

## Configuration

### 1. Environment

```dotenv
LICENSE_SERVER_URL=https://licences.example.com
LICENSE_INSTANCE_ID=ins_9f1c...
LICENSE_INSTANCE_SECRET=...
LICENSE_DOMAIN=customer.example.com
LICENSE_CACHE_DIR=/var/lib/license
```

`LICENSE_INSTANCE_ID` and `LICENSE_INSTANCE_SECRET` are issued by the licence server
when the deployment is created. The secret is the only credential the instance holds.
It never leaves the machine and is never transmitted.

### 2. Settings

```python
INSTALLED_APPS += ["license_client"]

MIDDLEWARE += ["license_client.middleware.LicenseEnforcementMiddleware"]

TEMPLATES[0]["OPTIONS"]["context_processors"] += [
    "license_client.context_processors.license_state",
]

LICENSE_SERVER_URL = env("LICENSE_SERVER_URL")
LICENSE_INSTANCE_ID = env("LICENSE_INSTANCE_ID")
LICENSE_INSTANCE_SECRET = env("LICENSE_INSTANCE_SECRET")
LICENSE_DOMAIN = env("LICENSE_DOMAIN")
LICENSE_CACHE_DIR = env("LICENSE_CACHE_DIR", default="/var/lib/license")
LICENSE_EXEMPT_URL_NAMES = ["login", "logout", "data_export"]
```

**Middleware ordering matters.** Place `LicenseEnforcementMiddleware` after
`SessionMiddleware` and `AuthenticationMiddleware`. A suspended customer should be able
to log in and read the suspension notice, rather than meeting an anonymous wall.

A misconfigured install fails `manage.py check` rather than starting up unlicensed.

### 3. Banner

Include once in your base template, inside `<body>`:

```django
{% include "license_client/banner.html" %}
```

It renders nothing while the subscription is healthy.

### 4. Scheduled refresh

With Celery:

```python
CELERY_BEAT_SCHEDULE["license-refresh"] = {
    "task": "license_client.refresh",
    "schedule": crontab(minute=17),
}
```

With cron:

```cron
17 * * * * cd /app && python manage.py license_refresh
```

Hourly is the recommended cadence. A token is valid for 72 hours, so an instance
survives roughly three days of failed refreshes — long enough to cover a weekend
outage, short enough that blocking the licence server is not a workaround.

### 5. Persist the cache directory

The token must outlive container rebuilds, or every deployment starts suspended:

```yaml
services:
  app:
    volumes:
      - license:/var/lib/license

volumes:
  license:
```

## Activation

```console
python manage.py license_refresh
python manage.py license_status
```

`license_status` prints the current access level, the reason for it, the paid-through
date and the token expiry. It must report `level: active` before the system is handed
over.

## Settings reference

| Setting | Required | Default | Purpose |
| --- | --- | --- | --- |
| `LICENSE_SERVER_URL` | yes | | Base URL of the licence server |
| `LICENSE_INSTANCE_ID` | yes | | Public identifier for this deployment |
| `LICENSE_INSTANCE_SECRET` | yes | | Shared secret; signs heartbeats, derives the token key |
| `LICENSE_DOMAIN` | yes | | Domain this licence is issued for; must match the token audience |
| `LICENSE_CACHE_DIR` | no | `/var/lib/license` | Where the token and rollback state are stored |
| `LICENSE_EXEMPT_PATHS` | no | `()` | Extra path prefixes that bypass enforcement |
| `LICENSE_EXEMPT_URL_NAMES` | no | `()` | URL names that bypass enforcement |

`/__license__/`, `/static/`, `/media/`, `/healthz` and `/favicon.ico` are always exempt.

## Exempting views

Three mechanisms, in the order the middleware checks them:

```python
# 1. Path prefix
LICENSE_EXEMPT_PATHS = ["/webhooks/"]

# 2. URL name
LICENSE_EXEMPT_URL_NAMES = ["login", "logout", "data_export"]

# 3. Decorator
from license_client.decorators import license_exempt

@license_exempt
def healthcheck(request):
    ...
```

Keep the list short. Every exemption is a hole in enforcement. The one you should not
omit is the route that lets a customer export their own records: a suspended customer
who cannot retrieve their data is a support problem and, depending on your agreement,
a legal one.

## Feature flags

Plans can carry feature flags, delivered in the token:

```python
from license_client.decorators import requires_feature

@requires_feature("advanced_reports")
def reports(request):
    ...
```

Returns 402 when the customer's plan does not include the feature.

## Monitoring

`GET /__license__/status` returns the current state as JSON, for your own monitoring.
It exposes no customer data:

```json
{
  "level": "active",
  "reason": "active",
  "period_end": "2026-09-30T23:59:59.999999+03:00"
}
```

Wire it into the URLconf:

```python
path("", include("license_client.urls")),
```

## Security properties

**Per-instance keys.** The token signing key is derived from the deployment's own
secret, `hmac_sha256(instance_secret, b"license-token-v1")`. Both sides run the same
derivation, so no key is stored twice and none is transmitted. Each token is verifiable
by exactly one instance. A leaked secret compromises that deployment and nothing else;
there is no master key.

**Replay protection.** Heartbeats are signed over a canonical string including a
timestamp, a single-use nonce and a hash of the body, so a captured signature cannot be
replayed or moved onto a different payload.

**Clock tampering.** The client records the highest `iat` it has seen. A token older
than that is refused, so winding the system clock back does not resurrect an expired
licence.

**Fails closed.** A missing token, an unverifiable token, a token addressed to another
domain or another instance, and a token past its expiry all resolve to suspended.

**Network failure fails open.** An unreachable licence server is an expected condition,
not an error. The cached token continues to apply until its tolerance window closes, and
a refresh that returns an unverifiable or already-expired token leaves the working
cached token in place.

## What this package does not do

**It is not tamper-proof.** If you ship source, a determined customer can remove the
middleware or forge a token using the secret already present on their server. The
technical control is friction that handles the ordinary case, which is a customer who
has simply not paid yet. The contract is the real protection against one who sets out
to defeat it.

**It does not phone home with customer data.** The heartbeat carries the instance id,
the application version, the hostname and the Django version. Nothing else.

## Development

```console
git clone https://github.com/islandkid-20/django-license-client
cd django-license-client
python -m venv venv && source venv/bin/activate
make install
make test
```

`make help` lists the available targets. `make check-sync` verifies that the token key
derivation in this package still matches the licence server's copy; the two must stay
byte-identical or every deployed instance will fail to verify its token.

## Licence

Proprietary. See [LICENSE](LICENSE). Where a signed service agreement exists, that
agreement governs.
