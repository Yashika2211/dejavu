"""What the model sees each turn, kept under the per-request token budget (spec 5.4).

The system prompt, the incident header (alert, time, memory briefing), a running summary of older
steps plus the current hypothesis board, and the last few steps verbatim. When a request would be
too large, fewer steps stay verbatim. Summary lines are deterministic digests of tool output, so
trimming never costs an extra model call.
"""

import json
from dataclasses import dataclass
from typing import Any

from dejavu.agent.schemas import AgentStep, Hypothesis
from dejavu.tokens import count_tokens


@dataclass(frozen=True)
class Turn:
    """One tool call and its result, as chat messages."""

    step: AgentStep
    assistant: dict[str, Any]
    tool: dict[str, Any]


def digest(step: AgentStep) -> str:
    """A one-line summary of a step for the running summary."""
    lines = [line.strip() for line in step.output.splitlines() if line.strip()]
    args = ", ".join(f"{k}={v}" for k, v in step.args.items())
    return f"#{step.index} {step.tool}({args[:90]}) -> {' | '.join(lines[:3])}"[:300]


def board_text(board: list[Hypothesis]) -> str:
    return "\n".join(
        f"- {h.id} p={h.probability:.2f} {h.category.value} in {h.service}: {h.statement[:120]}"
        for h in board
    )


def wrap_output(tool: str, output: str) -> str:
    return f'<tool_output source="{tool}" untrusted="true">\n{output}\n</tool_output>'


class ContextBuilder:
    def __init__(
        self, system: str, header: str, *, tools: list[dict[str, Any]], budget_tokens: int, verbatim: int = 4
    ) -> None:
        self.system = system
        self.header = header
        self.tools_tokens = count_tokens(json.dumps(tools))
        self.budget = budget_tokens
        self.verbatim = verbatim

    def build(self, turns: list[Turn], board: list[Hypothesis], *, verbatim: int) -> list[dict[str, Any]]:
        keep = turns[-verbatim:] if verbatim > 0 else []
        older = turns[: len(turns) - len(keep)]
        parts = [self.header]
        if older:
            parts.append("Earlier steps (summarised):\n" + "\n".join(digest(t.step) for t in older))
        if board:
            parts.append("Current hypothesis board:\n" + board_text(board))
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": self.system},
            {"role": "user", "content": "\n\n".join(parts)},
        ]
        for turn in keep:
            messages += [turn.assistant, turn.tool]
        return messages

    def tokens(self, messages: list[dict[str, Any]]) -> int:
        return count_tokens(json.dumps(messages)) + self.tools_tokens

    def fit(
        self, turns: list[Turn], board: list[Hypothesis], *, max_verbatim: int | None = None
    ) -> list[dict[str, Any]]:
        """The richest message list under the budget (fewest verbatim steps as a floor)."""
        start = self.verbatim if max_verbatim is None else max_verbatim
        for verbatim in range(start, -1, -1):
            messages = self.build(turns, board, verbatim=verbatim)
            if self.tokens(messages) <= self.budget:
                return messages
        return messages
