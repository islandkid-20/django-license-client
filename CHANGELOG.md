# Changelog

This project follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

The licence token contract is versioned separately from the package. A change to
`lic.v` is a breaking change for every deployed instance and will only ever accompany a
major release.

## [1.0.0] — 2026-08-04

First release.

### Added

- `LicenseEnforcementMiddleware`, applying the four access levels: active, grace,
  read-only and suspended.
- Local token verification with no network call in the request path. HS256 over a key
  derived from the deployment's own secret, so a token is verifiable by exactly one
  instance.
- Signed heartbeat transport with timestamp, single-use nonce and body hash, so a
  captured signature cannot be replayed or moved onto another payload.
- Rollback protection: the highest `iat` seen is persisted, and older tokens are
  refused.
- `license_refresh` and `license_status` management commands.
- `license_exempt` and `requires_feature` view decorators, plus path-prefix and
  URL-name exemptions. `license_exempt` works on function views, class-based and DRF
  view classes, and the result of `as_view()`.
- Django REST Framework support. Refusals follow content negotiation and return JSON
  with a stable `code` when the caller asks for it, and the notice page otherwise, so
  DRF's browsable API keeps working. `LICENSE_API_PATHS` forces JSON for clients that
  send no usable `Accept` header.
- Optional `license_client.drf` with `IsLicensed` and `HasLicenseFeature` permission
  classes, raising 402 with the same body the middleware produces. DRF stays an
  optional dependency; nothing imports it unless a product does.
- Suspension and read-only notice pages, self-contained so they render when the rest
  of the application is unreachable. These are the only screens this package renders,
  and only when a request is refused; nothing is injected into a working interface.
- `GET /__license__/status` for monitoring.
- Startup configuration check, so a misconfigured install fails `manage.py check`
  rather than running unlicensed.

### Notes

- `verify()` requires `exp` to be present but does not reject on it. Expiry is the
  offline tolerance window, and `License.is_stale` owns that decision so callers can
  distinguish a token that aged out from one that is forged.
- `refresh_license` refuses to store an unverifiable or already-expired token, leaving
  the working cached token in place.
