"""Secret-shaped strings generated at runtime from a seed.

Nothing secret-shaped is ever committed (GitHub push protection would block it); leaked-token
test cases build theirs here, deterministically, when they run.
"""

import base64
import json
import random


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def fake_jwt(seed: int, *, subject: str = "svc-checkout-api") -> str:
    """A syntactically valid, meaningless HS256 JWT. Same seed, same token."""
    rng = random.Random(seed)
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {
        "sub": subject,
        "iss": "auth-svc.prod",
        "iat": 1_786_000_000 + rng.randrange(10_000_000),
        "jti": f"{rng.getrandbits(64):016x}",
    }
    signature = rng.randbytes(32)
    return ".".join(
        (
            _b64url(json.dumps(header, separators=(",", ":")).encode()),
            _b64url(json.dumps(payload, separators=(",", ":")).encode()),
            _b64url(signature),
        )
    )
