"""Defense in depth for what flows from telemetry into prompts and memory.

Tool outputs are untrusted: log lines can carry attacker-controlled text (a User-Agent addressed
to "AI agents") and credentials leaked by debug logging. Before any of it reaches a model or the
memory bank, secrets are redacted and instruction-shaped text aimed at agents is neutralised.
The system prompt also tells the model to treat tool output as data; this is the second layer,
and Hindsight's Memory Defense is the third.
"""

import re

_SECRETS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("jwt", re.compile(r"\beyJ[\w-]{8,}\.eyJ[\w-]{8,}\.[\w-]{8,}")),
    ("bearer_token", re.compile(r"(?i)\bbearer\s+[\w\-.~+/]{20,}=*")),
    ("groq_key", re.compile(r"\bgsk_[A-Za-z0-9]{20,}")),
    ("openai_key", re.compile(r"\bsk-(?:proj-|admin-)?[A-Za-z0-9_-]{20,}")),
    ("github_token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}")),
    ("aws_access_key", re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b")),
    (
        "private_key",
        re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----"),
    ),
    ("db_url", re.compile(r"\b(?:postgres(?:ql)?|mysql|mongodb(?:\+srv)?)://[^\s:@/]+:[^\s@/]+@\S+")),
)

# Text that addresses an AI agent or tries to steer tool use. Legitimate telemetry never does this.
_INJECTION = re.compile(
    r"(?i)(#{2,}\s*)?(system\s+notice|ignore\s+(all\s+)?(previous|prior)\s+instructions|"
    r"(to|attention)\s+(all\s+)?(ai|llm)\s+agents?|you\s+are\s+now\s+|"
    r"(immediately\s+)?call\s+(run_remediation|submit_diagnosis|page_human)\b)[^\n\"]*"
)
INJECTION_MARKER = "[untrusted text resembling instructions to an AI agent removed]"


def redact_secrets(text: str) -> str:
    """Replace credentials with `[REDACTED:<kind>]` markers."""
    for kind, pattern in _SECRETS:
        text = pattern.sub(f"[REDACTED:{kind}]", text)
    return text


def neutralize_injections(text: str) -> str:
    """Remove instruction-shaped text aimed at agents, leaving the rest of the line intact."""
    return _INJECTION.sub(INJECTION_MARKER, text)


def sanitize(text: str) -> str:
    """Both, in the order that keeps markers readable."""
    return neutralize_injections(redact_secrets(text))
