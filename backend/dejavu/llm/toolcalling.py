"""One tool call per turn, whatever the model does (spec 5.4).

Ask the model for a tool call. If Groq rejects the call (`tool_use_failed`), try to salvage the
failed generation into a valid call; if it was plain text, re-prompt with a corrective note. After
two failures on one model, fall back to the next. As a last resort, emulate tool calling in JSON
mode (`{"tool": ..., "args": {...}}`). A misbehaving model never crashes a run: the caller gets a
decision, or `NoDecisionError` once every model and mode has failed.
"""

import json
import re
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel

from dejavu.llm.client import LLMClient, LLMResponse
from dejavu.llm.errors import LLMError, ModelUnavailableError, RetriesExhaustedError, ToolUseFailedError

RATIONALE = {
    "type": "string",
    "description": "Why this step, in at most 25 words. Shown to the on-call human.",
}
REPROMPT = "Reply with exactly one tool call and nothing else. Call submit_diagnosis when you are done."


class NoDecisionError(LLMError):
    """Every model, repair and JSON-mode attempt failed to produce a tool call."""


@dataclass(frozen=True)
class ToolSpec:
    """A tool as the model sees it."""

    name: str
    description: str
    parameters: dict[str, Any]

    def as_openai(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {"name": self.name, "description": self.description, "parameters": self.parameters},
        }


@dataclass(frozen=True)
class Call:
    id: str
    name: str
    args: dict[str, Any]


@dataclass
class Decision:
    calls: list[Call]
    model: str
    content: str | None = None
    notes: list[str] = field(default_factory=list)

    @property
    def repaired(self) -> bool:
        return bool(self.notes)


def _inline_refs(node: Any, defs: dict[str, Any]) -> Any:
    if isinstance(node, dict):
        if "$ref" in node:
            return _inline_refs(defs[node["$ref"].split("/")[-1]], defs)
        return {k: _inline_refs(v, defs) for k, v in node.items() if k not in ("title", "$defs")}
    if isinstance(node, list):
        return [_inline_refs(v, defs) for v in node]
    return node


def inline_schema(model: type[BaseModel]) -> dict[str, Any]:
    """The model's JSON schema with every `$ref` inlined. Hindsight's reflect flattens nested
    objects to strings when they sit behind `$defs` (live, 29 Sep), and Groq tools want them inline."""
    schema = model.model_json_schema()
    return {"title": schema.get("title", model.__name__), **_inline_refs(schema, schema.get("$defs", {}))}


def tool_spec(name: str, description: str, args: type[BaseModel]) -> ToolSpec:
    """A tool definition from a Pydantic model, with a required `rationale` and refs inlined."""
    params = inline_schema(args)
    params.pop("title", None)
    params.setdefault("properties", {})["rationale"] = RATIONALE
    params["required"] = [*params.get("required", []), "rationale"]
    params["type"] = "object"
    return ToolSpec(name, description, params)


# salvaging ---------------------------------------------------------------------------------------------

_HARMONY = re.compile(r"to=functions\.(\w+)")
_TAGGED = re.compile(r"<function=(\w+)>")
_CALLISH = re.compile(r"functions\.(\w+)\s*\(")


def _first_json_object(text: str, start: int = 0) -> dict[str, Any] | None:
    """The first `{...}` at or after `start`, closing unbalanced braces if the model stopped early."""
    i = text.find("{", start)
    if i < 0:
        return None
    depth, in_str, escaped = 0, False, False
    for j in range(i, len(text)):
        ch = text[j]
        if in_str:
            escaped = ch == "\\" and not escaped
            if ch == '"' and not escaped:
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return _loads(text[i : j + 1])
    return _loads(text[i:] + ('"' if in_str else "") + "}" * depth)


def _loads(raw: str) -> dict[str, Any] | None:
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None


def salvage(text: str, tool_names: set[str]) -> tuple[str, dict[str, Any]] | None:
    """Recover a tool call from a malformed generation, or None if there is nothing to recover."""
    whole = _first_json_object(text)
    if whole:
        name = whole.get("name") or whole.get("tool") or whole.get("function")
        args = whole.get("arguments", whole.get("args", whole.get("parameters")))
        if isinstance(args, str):
            args = _loads(args)
        if name in tool_names and isinstance(args, dict):
            return str(name), args
    for pattern in (_HARMONY, _TAGGED, _CALLISH):
        m = pattern.search(text)
        if m and m.group(1) in tool_names:
            args = _first_json_object(text, m.end())
            return m.group(1), args or {}
    for name in tool_names:
        at = text.find(name)
        if at >= 0 and (args := _first_json_object(text, at)) is not None:
            return name, args
    return None


# the policy --------------------------------------------------------------------------------------------


class ToolCaller:
    """Gets one usable tool call per turn out of a chain of models."""

    def __init__(
        self,
        client: LLMClient,
        models: list[str],
        *,
        reasoning_effort: str | None = "medium",
        temperature: float = 0.2,
        max_tokens: int = 1200,
        attempts_per_model: int = 2,
    ) -> None:
        if not models:
            raise ValueError("at least one model is required")
        self.client = client
        self.models = models
        self.reasoning_effort = reasoning_effort
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.attempts_per_model = attempts_per_model

    async def decide(
        self, messages: list[dict[str, Any]], tools: list[ToolSpec], *, purpose: str = "agent"
    ) -> Decision:
        names = {t.name for t in tools}
        notes: list[str] = []
        for model in self.models:
            convo = list(messages)
            for _ in range(self.attempts_per_model):
                try:
                    resp = await self.client.complete(
                        model=model,
                        messages=convo,
                        tools=[t.as_openai() for t in tools],
                        tool_choice="required",
                        temperature=self.temperature,
                        max_tokens=self.max_tokens,
                        reasoning_effort=self.reasoning_effort,
                        purpose=purpose,
                    )
                except ToolUseFailedError as exc:
                    salvaged = salvage(exc.failed_generation, names)
                    if salvaged:
                        notes.append(f"{model}: tool_use_failed, salvaged {salvaged[0]}")
                        return Decision([Call(f"salvaged-{len(notes)}", *salvaged)], model, None, notes)
                    notes.append(f"{model}: tool_use_failed, re-prompting")
                    convo += [
                        {"role": "user", "content": f"Your last tool call could not be parsed. {REPROMPT}"}
                    ]
                    continue
                except (ModelUnavailableError, RetriesExhaustedError) as exc:
                    notes.append(f"{model}: {exc}")
                    break
                calls = _parse_calls(resp, names)
                if calls:
                    return Decision(calls, model, resp.content, notes)
                notes.append(f"{model}: replied without a tool call, re-prompting")
                convo += [
                    {"role": "assistant", "content": resp.content or ""},
                    {"role": "user", "content": REPROMPT},
                ]
            notes.append(f"{model}: falling back")
        return await self._json_mode(messages, tools, notes, purpose)

    async def _json_mode(
        self, messages: list[dict[str, Any]], tools: list[ToolSpec], notes: list[str], purpose: str
    ) -> Decision:
        catalog = "\n".join(
            f"- {t.name}: {t.description} Arguments: {json.dumps(t.parameters.get('properties', {}))}"
            for t in tools
        )
        instruction = (
            "Tool calling is unavailable. Choose exactly one tool and answer with a JSON object "
            f'{{"tool": "<name>", "args": {{...}}}} and nothing else. Tools:\n{catalog}'
        )
        for model in self.models:
            try:
                resp = await self.client.complete(
                    model=model,
                    messages=[*messages, {"role": "user", "content": instruction}],
                    response_format={"type": "json_object"},
                    temperature=self.temperature,
                    max_tokens=self.max_tokens,
                    purpose=f"{purpose}:json-mode",
                )
            except LLMError as exc:
                notes.append(f"{model}: json mode failed ({exc})")
                continue
            found = salvage(resp.content or "", {t.name for t in tools})
            if found:
                notes.append(f"{model}: json-mode emulation")
                return Decision([Call("json-mode", *found)], model, None, notes)
            notes.append(f"{model}: json mode returned no tool")
        raise NoDecisionError("; ".join(notes))


def _parse_calls(resp: LLMResponse, names: set[str]) -> list[Call]:
    calls = []
    for tc in resp.tool_calls:
        if tc.name not in names:
            continue
        args = _loads(tc.arguments) if tc.arguments.strip() else {}
        if args is None:
            recovered = salvage(f'{{"name": "{tc.name}", "arguments": {tc.arguments}}}', names)
            args = recovered[1] if recovered else {}
        calls.append(Call(tc.id, tc.name, args))
    return calls
