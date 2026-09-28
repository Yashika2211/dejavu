"""Failures the LLM layer distinguishes. Everything retryable is retried inside the client;
what reaches the caller is something only the caller can fix (trim context, repair a tool call,
fall back to another model)."""


class LLMError(Exception):
    """Base class for LLM-layer failures."""


class ToolUseFailedError(LLMError):
    """Groq rejected the model's tool call (HTTP 400, `tool_use_failed`); `failed_generation` is raw."""

    def __init__(self, model: str, failed_generation: str) -> None:
        super().__init__(f"{model}: tool_use_failed")
        self.model = model
        self.failed_generation = failed_generation


class ContextTooLongError(LLMError):
    """HTTP 413 or a context-length 400: the caller must trim the conversation."""


class ModelUnavailableError(LLMError):
    """The model does not exist for this key, was decommissioned, or keeps failing."""


class RetriesExhaustedError(LLMError):
    """Rate limits or server errors outlasted the retry budget."""
