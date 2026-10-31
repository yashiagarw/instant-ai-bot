"""LLM providers for the live layer: one call = one strict tool the model must call.

ClaudeProvider calls the Claude API (Anthropic Python SDK, no retries: the caller has a ~4 s budget).
FakeProvider answers from a function, for tests; it never touches the network.
"""

from __future__ import annotations

import base64
import json
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Protocol


class LLMError(Exception):
    """The call failed (network, API error). The caller falls back."""


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    schema: dict


@dataclass
class LLMRequest:
    model: str
    system: str
    user: str
    tool: ToolSpec
    max_tokens: int
    effort: str = "low"
    # (media type, bytes) images sent before the text, e.g. a customer photo (already re-encoded, no metadata).
    images: list[tuple[str, bytes]] = field(default_factory=list)


@dataclass
class LLMResponse:
    data: dict | None  # the tool input; None when the model did not call the tool
    model: str
    stop_reason: str | None = None  # tool_use, end_turn, max_tokens, refusal, ...
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0


class LLMProvider(Protocol):
    name: str

    def call(self, request: LLMRequest) -> LLMResponse: ...


class ClaudeProvider:
    name = "anthropic"

    def __init__(self, api_key: str, timeout: float):
        import anthropic

        self._anthropic = anthropic
        # The SDK timeout is a backstop so a call abandoned by the caller's wall-clock timeout still ends.
        self.client = anthropic.Anthropic(api_key=api_key, timeout=timeout + 2, max_retries=0)

    def call(self, request: LLMRequest) -> LLMResponse:
        try:
            r = self.client.messages.create(
                model=request.model,
                max_tokens=request.max_tokens,
                system=request.system,
                output_config={"effort": request.effort},
                tools=[
                    {
                        "name": request.tool.name,
                        "description": request.tool.description,
                        "input_schema": request.tool.schema,
                        "strict": True,
                    }
                ],
                # Forced tool_choice is rejected on several current models: auto + the prompt's instruction.
                tool_choice={"type": "auto"},
                messages=[{"role": "user", "content": _content(request)}],
            )
        except self._anthropic.APIError as e:
            raise LLMError(f"{type(e).__name__}: {getattr(e, 'status_code', '')}".strip(": ")) from e
        data = None
        if r.stop_reason not in ("refusal", "max_tokens"):
            for block in r.content:
                if block.type == "tool_use" and block.name == request.tool.name:
                    data = block.input if isinstance(block.input, dict) else json.loads(block.input)
                    break
        u = r.usage
        return LLMResponse(
            data=data,
            model=r.model,
            stop_reason=r.stop_reason,
            input_tokens=u.input_tokens or 0,
            output_tokens=u.output_tokens or 0,
            cache_read_tokens=getattr(u, "cache_read_input_tokens", 0) or 0,
            cache_write_tokens=getattr(u, "cache_creation_input_tokens", 0) or 0,
        )


def _content(request: LLMRequest) -> str | list[dict]:
    if not request.images:
        return request.user
    blocks: list[dict] = [
        {"type": "image", "source": {"type": "base64", "media_type": t, "data": base64.b64encode(b).decode()}}
        for t, b in request.images
    ]
    return [*blocks, {"type": "text", "text": request.user}]


@dataclass
class FakeProvider:
    """`respond(request) -> tool input dict` (or None = no tool call). `delay` seconds before answering, `error`
    raised instead of answering, `stop_reason` reported (e.g. "refusal")."""

    respond: Callable[[LLMRequest], dict | None] = lambda request: None
    delay: float = 0.0
    error: Exception | None = None
    stop_reason: str = "tool_use"
    input_tokens: int = 300
    output_tokens: int = 40
    name: str = "fake"
    requests: list[LLMRequest] = field(default_factory=list)

    def call(self, request: LLMRequest) -> LLMResponse:
        self.requests.append(request)
        if self.delay:
            time.sleep(self.delay)
        if self.error is not None:
            raise self.error
        data = None if self.stop_reason == "refusal" else self.respond(request)
        return LLMResponse(
            data=data,
            model=request.model,
            stop_reason=self.stop_reason,
            input_tokens=self.input_tokens,
            output_tokens=self.output_tokens,
        )
