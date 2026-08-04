"""Must stay byte-identical to apps/licensing/signing.py on the server."""

import hashlib
import hmac

TOKEN_KEY_LABEL = b"license-token-v1"


def derive_token_key(instance_secret: str) -> bytes:
    return hmac.new(instance_secret.encode(), TOKEN_KEY_LABEL, hashlib.sha256).digest()
