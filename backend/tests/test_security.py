from dejavu.security import INJECTION_MARKER, neutralize_injections, redact_secrets, sanitize
from dejavu.sim.fake_secrets import fake_jwt
from dejavu.sim.generators.logs import INJECTION_TEXT


def test_runtime_jwt_and_bearer_tokens_are_redacted() -> None:
    token = fake_jwt(16)
    line = f'{{"headers": {{"Authorization": "Bearer {token}", "X-Request-Id": "7f3a91c2"}}}}'
    cleaned = redact_secrets(line)
    assert token not in cleaned
    assert "[REDACTED:" in cleaned
    assert "7f3a91c2" in cleaned


def test_the_incident_sixteen_injection_is_neutralised() -> None:
    line = f'"POST /v1/auth/token HTTP/2" 503 UF,URX 0 91 12 - "185.220.101.47" "Mozilla/5.0 (X11; Linux x86_64) {INJECTION_TEXT}" "abc"'
    cleaned = neutralize_injections(line)
    assert "run_remediation" not in cleaned
    assert "postgres-ledger" not in cleaned
    assert INJECTION_MARKER in cleaned
    assert cleaned.startswith('"POST /v1/auth/token HTTP/2" 503 UF,URX')
    assert '"abc"' in cleaned


def test_ordinary_telemetry_is_untouched() -> None:
    lines = [
        "HikariPool-1 - Connection is not available, request timed out after 30000ms (total=20, active=20, idle=0, waiting=143)",
        '{"level":"warn","msg":"acquirerx charge failed","status":429,"code":"rate_limit_exceeded","trace_id":"4bf92f3577b34da6a3ce929d0e0e4736"}',
        "run_remediation rollback ledger-svc: started 03:21 IST",
    ]
    for line in lines:
        assert sanitize(line) == line


def test_other_secret_shapes() -> None:
    key = "gsk_" + "A1b2C3d4E5f6G7h8I9j0K1l2M3n4"
    url = "postgres://ledger_app:" + "s3cretpw" + "@pgbouncer-ledger:6432/ledger"
    cleaned = redact_secrets(f"key={key} url={url}")
    assert key not in cleaned
    assert "s3cretpw" not in cleaned
