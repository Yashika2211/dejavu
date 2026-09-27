import base64
import json
import re

from dejavu.sim.fake_secrets import fake_jwt

JWT_SHAPE = re.compile(r"^eyJ[\w-]+\.eyJ[\w-]+\.[\w-]+$")


def _decode(segment: str) -> dict:
    return json.loads(base64.urlsafe_b64decode(segment + "=" * (-len(segment) % 4)))


def test_same_seed_same_token() -> None:
    assert fake_jwt(16) == fake_jwt(16)


def test_different_seeds_differ() -> None:
    assert fake_jwt(16) != fake_jwt(17)


def test_token_is_jwt_shaped_so_memory_defense_can_catch_it() -> None:
    token = fake_jwt(42, subject="svc-ledger")
    assert JWT_SHAPE.match(token)
    header, payload, _ = token.split(".")
    assert _decode(header) == {"alg": "HS256", "typ": "JWT"}
    assert _decode(payload)["sub"] == "svc-ledger"
