"""LLM providers for the offline structuring step. The live app never imports this module.

AnthropicProvider calls the Claude API with one strict tool and returns the tool input.
OpenAIProvider calls the OpenAI Responses API with the same JSON schema as strict structured output.
FakeProvider builds a valid answer from the request context, for tests.
make_provider() picks one from LLM_PROVIDER (or the CLI's --provider).
"""

import hashlib
import json
import threading
from dataclasses import dataclass, field
from typing import Any, Protocol

# USD per million tokens: input, output, cache read, 5-minute cache write.
PRICES = {
    "claude-opus-5-5": (4.00, 20.00, 0.20, 5.00),
    "claude-opus-5": (5.00, 25.00, 0.50, 6.25),
    "claude-opus-4-8": (5.00, 25.00, 0.50, 6.25),
    "claude-sonnet-5-5": (2.00, 10.00, 0.20, 2.50),
    "claude-haiku-5-5": (0.10, 0.50, 0.01, 0.125),
}


class LLMError(Exception):
    """The model did not return a usable tool call (refusal, truncation, no call after retry)."""


@dataclass
class Usage:
    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_input_tokens: int = 0
    cache_creation_input_tokens: int = 0
    fallbacks: int = 0
    models: set[str] = field(default_factory=set)
    # (input, output, cache read, cache write) USD per million tokens; None = look up PRICES by model.
    prices: tuple[float, float, float, float] | None = None
    # Anthropic reports input_tokens without cached tokens; OpenAI's input_tokens includes them.
    input_includes_cached: bool = False
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def add(self, usage: Any, model: str, fell_back: bool) -> None:
        """Anthropic-shaped usage object (input_tokens excludes cached tokens)."""
        self.add_counts(
            model,
            input_tokens=getattr(usage, "input_tokens", 0) or 0,
            output_tokens=getattr(usage, "output_tokens", 0) or 0,
            cache_read=getattr(usage, "cache_read_input_tokens", 0) or 0,
            cache_write=getattr(usage, "cache_creation_input_tokens", 0) or 0,
            fell_back=fell_back,
        )

    def add_counts(
        self,
        model: str,
        input_tokens: int,
        output_tokens: int,
        cache_read: int = 0,
        cache_write: int = 0,
        fell_back: bool = False,
    ) -> None:
        """input_tokens as the provider reports it (see input_includes_cached)."""
        with self._lock:
            self.calls += 1
            self.input_tokens += input_tokens
            self.output_tokens += output_tokens
            self.cache_read_input_tokens += cache_read
            self.cache_creation_input_tokens += cache_write
            self.fallbacks += int(fell_back)
            self.models.add(model)

    def cost_usd(self, model: str) -> float | None:
        """Estimate at the requested model's prices (a fallback hop bills at its own model's rates)."""
        prices = self.prices or PRICES.get(model)
        if prices is None:
            return None
        p_in, p_out, p_read, p_write = prices
        # Bill each token once: cached tokens at the cache-read price, the rest at the input price.
        uncached = self.input_tokens - self.cache_read_input_tokens if self.input_includes_cached else self.input_tokens
        return round(
            (
                max(0, uncached) * p_in
                + self.output_tokens * p_out
                + self.cache_read_input_tokens * p_read
                + self.cache_creation_input_tokens * p_write
            )
            / 1_000_000,
            4,
        )

    def as_dict(self, model: str) -> dict:
        return {
            "calls": self.calls,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cache_read_input_tokens": self.cache_read_input_tokens,
            "cache_creation_input_tokens": self.cache_creation_input_tokens,
            "fallback_calls": self.fallbacks,
            "served_by": sorted(self.models),
            "cost_usd_estimate": self.cost_usd(model),
        }


@dataclass
class ToolRequest:
    """One structuring call: a strict tool the model must call, cached system blocks, the per-item text."""

    tool_name: str
    tool_description: str
    schema: dict
    system_static: str  # identical for every call of this kind (cached)
    system_category: str  # identical within one category (cached)
    user_text: str
    context: dict  # structured copy of the inputs (used by FakeProvider and for logging)


class LLMProvider(Protocol):
    name: str
    model: str
    usage: Usage

    def call(self, request: ToolRequest) -> dict: ...


class AnthropicProvider:
    def __init__(self, model: str, effort: str, api_key: str = "", max_tokens: int = 16000):
        import anthropic  # offline dependency, imported only when used

        self._anthropic = anthropic
        self.client = anthropic.Anthropic(api_key=api_key) if api_key else anthropic.Anthropic()
        self.name = "anthropic"
        self.model = model
        self.effort = effort
        self.max_tokens = max_tokens
        self.usage = Usage()

    def _create(self, request: ToolRequest, messages: list[dict]):
        return self.client.beta.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            # Refusals are re-run server-side on Anthropic's recommended fallback model.
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            output_config={"effort": self.effort},
            # Tools render before system: tools + both system blocks form the cached prefix.
            system=[
                {"type": "text", "text": request.system_static},
                {"type": "text", "text": request.system_category, "cache_control": {"type": "ephemeral"}},
            ],
            tools=[
                {
                    "name": request.tool_name,
                    "description": request.tool_description,
                    "input_schema": request.schema,
                    "strict": True,
                }
            ],
            # Forced tool_choice is rejected on this model family: auto + an explicit instruction + retry.
            tool_choice={"type": "auto"},
            messages=messages,
        )

    def call(self, request: ToolRequest) -> dict:
        messages = [{"role": "user", "content": request.user_text}]
        for attempt in range(2):
            response = self._create(request, messages)
            fell_back = any(getattr(i, "type", "") == "fallback_message" for i in (response.usage.iterations or []))
            self.usage.add(response.usage, response.model, fell_back)
            if response.stop_reason == "refusal":
                category = getattr(response.stop_details, "category", None) if response.stop_details else None
                raise LLMError(f"refused (category {category})")
            if response.stop_reason == "max_tokens":
                raise LLMError("output hit max_tokens")
            for block in response.content:
                if block.type == "tool_use" and block.name == request.tool_name:
                    return block.input if isinstance(block.input, dict) else json.loads(block.input)
            if attempt == 0:  # no tool call: ask once more, appending to the conversation
                messages = messages + [
                    {"role": "assistant", "content": response.content},
                    {"role": "user", "content": f"Please answer by calling the {request.tool_name} tool."},
                ]
        raise LLMError(f"no {request.tool_name} call after a retry")


def check_schema(value: Any, schema: dict, path: str = "$") -> None:
    """Validate a parsed answer against the strict-schema subset used in prompts.py
    (object, array, string, boolean, integer, number, enum). Raises LLMError on the first mismatch."""
    kind = schema.get("type")
    if "enum" in schema and value not in schema["enum"]:
        raise LLMError(f"{path}: {value!r} is not one of the allowed values")
    if kind == "object":
        if not isinstance(value, dict):
            raise LLMError(f"{path}: expected an object")
        props = schema.get("properties", {})
        missing = [k for k in schema.get("required", []) if k not in value]
        extra = [k for k in value if k not in props] if schema.get("additionalProperties") is False else []
        if missing or extra:
            raise LLMError(f"{path}: missing {missing}, unexpected {extra}")
        for k, sub in props.items():
            if k in value:
                check_schema(value[k], sub, f"{path}.{k}")
    elif kind == "array":
        if not isinstance(value, list):
            raise LLMError(f"{path}: expected an array")
        for i, item in enumerate(value):
            check_schema(item, schema.get("items", {}), f"{path}[{i}]")
    elif kind == "string" and not isinstance(value, str):
        raise LLMError(f"{path}: expected a string")
    elif kind == "boolean" and not isinstance(value, bool):
        raise LLMError(f"{path}: expected true/false")
    elif kind == "integer" and (not isinstance(value, int) or isinstance(value, bool)):
        raise LLMError(f"{path}: expected an integer")
    elif kind == "number" and (not isinstance(value, (int, float)) or isinstance(value, bool)):
        raise LLMError(f"{path}: expected a number")


class OpenAIProvider:
    """OpenAI Responses API with strict structured output (the ToolRequest schema as text.format).

    The answer arrives as JSON text, so it is parsed and checked against the same schema locally.
    """

    def __init__(
        self,
        model: str,
        api_key: str = "",
        reasoning_effort: str = "",
        prices: tuple[float, float, float, float] | None = None,
        max_output_tokens: int = 16000,
    ):
        import openai  # offline dependency, imported only when used

        if not model:
            raise LLMError("OPENAI_MODEL is not set in backend/.env")
        self.client = openai.OpenAI(api_key=api_key) if api_key else openai.OpenAI()
        self.name = "openai"
        self.model = model
        self.effort = reasoning_effort or None
        self.max_output_tokens = max_output_tokens
        self.usage = Usage(prices=prices, input_includes_cached=True)

    def _create(self, request: ToolRequest, extra_input: list[dict]):
        kwargs: dict[str, Any] = {
            "model": self.model,
            # Same split as the Claude provider: the stable text comes first so the provider's prompt
            # cache can reuse it across the faults of one category.
            "instructions": f"{request.system_static}\n\n{request.system_category}",
            "input": [{"role": "user", "content": request.user_text}, *extra_input],
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": request.tool_name,
                    "description": request.tool_description,
                    "schema": request.schema,
                    "strict": True,
                }
            },
            "max_output_tokens": self.max_output_tokens,
            "store": False,
            "prompt_cache_key": f"autocare:{request.tool_name}:"
            f"{hashlib.sha1(request.system_category.encode()).hexdigest()[:10]}",
        }
        if self.effort:  # only reasoning models accept this; unset = the model's default
            kwargs["reasoning"] = {"effort": self.effort}
        return self.client.responses.create(**kwargs)

    def _record(self, response) -> None:
        u = response.usage
        if u is None:
            self.usage.add_counts(response.model or self.model, 0, 0)
            return
        details = getattr(u, "input_tokens_details", None)
        # input_tokens as reported (it already includes the cached part); cached from the details.
        # OpenAI caching has no separate write charge, so cache writes are always 0.
        self.usage.add_counts(
            response.model or self.model,
            input_tokens=u.input_tokens or 0,
            output_tokens=u.output_tokens or 0,
            cache_read=(getattr(details, "cached_tokens", 0) or 0) if details else 0,
            cache_write=0,
        )

    def call(self, request: ToolRequest) -> dict:
        extra: list[dict] = []
        problem = "no answer"
        for attempt in range(2):
            response = self._create(request, extra)
            self._record(response)
            for item in response.output or []:
                for content in getattr(item, "content", None) or []:
                    if getattr(content, "type", "") == "refusal":
                        raise LLMError(f"refused ({content.refusal[:120]})")
            if response.status == "incomplete":
                reason = getattr(response.incomplete_details, "reason", None)
                if reason == "content_filter":
                    raise LLMError("refused (content filter)")
                raise LLMError(f"output incomplete ({reason})")
            if response.status not in (None, "completed"):
                raise LLMError(f"response status {response.status}")
            text = response.output_text
            try:
                answer = json.loads(text)
                check_schema(answer, request.schema)
                return answer
            except (json.JSONDecodeError, LLMError) as e:
                problem = f"invalid JSON answer ({e})"
            if attempt == 0:  # ask once more, showing what was wrong
                extra = [
                    {"role": "assistant", "content": text or "(empty)"},
                    {
                        "role": "user",
                        "content": f"That answer was not valid: {problem}. Reply with JSON that "
                        f"matches the {request.tool_name} schema exactly.",
                    },
                ]
        raise LLMError(f"{problem} after a retry")


class FakeProvider:
    """Deterministic answers built from the request context. Never calls a network."""

    name = "fake"

    def __init__(self, model: str = "fake-model"):
        self.model = model
        self.usage = Usage()
        self.requests: list[ToolRequest] = []

    def call(self, request: ToolRequest) -> dict:
        self.requests.append(request)
        self.usage.add(type("U", (), {"input_tokens": 100, "output_tokens": 50})(), self.model, False)
        ctx = request.context
        if request.tool_name == "propose_stage2_choices":
            keys = [f["fault_key"] for f in ctx["faults"]]
            half = max(1, len(keys) // 2)
            return {
                "question_text": "What problem are you facing?",
                "choices": [
                    {"label": "Main problem A", "fault_keys": keys[:half]},
                    {"label": "Main problem B", "fault_keys": keys[half:] or keys[:1]},
                ],
            }
        if request.tool_name == "structure_fault":
            fault = ctx["fault"]
            symptoms = fault["symptoms"] or [fault["name"]]
            out = {
                "stage2_choices": ctx["choices"][:1],
                "follow_up_questions": [
                    {
                        "text": f"Do you notice this: {symptoms[0]}?",
                        "source": "symptoms",
                        "options": [
                            {"label": "Yes", "effect": "supports", "strength": "strong", "safety_trigger": False},
                            {"label": "No", "effect": "rules_out", "strength": "moderate", "safety_trigger": False},
                        ],
                    },
                    {
                        "text": "Is there smoke or a burning smell?",
                        "source": "stages_text",
                        "options": [
                            {"label": "Yes", "effect": "neutral", "strength": "none", "safety_trigger": True},
                            {"label": "No", "effect": "neutral", "strength": "none", "safety_trigger": False},
                            {"label": "Not sure", "effect": "neutral", "strength": "none", "safety_trigger": False},
                        ],
                    },
                ],
                "confirmation_test": f"Mechanic confirms: {fault['likely_fault'] or fault['name']}",
                "danger_phrases": ["smoke", "burning smell"],
            }
            if ctx.get("draft_safety"):
                out["safety_rule"] = {
                    "risk_level": "high" if "danger" in fault["name"].lower() else "medium",
                    "stop_driving_trigger": fault["safety_precautions"][:120] or "Stop if unsafe.",
                    "roadside_action": "Follow the safety precautions.",
                    "towing_recommendation": fault["towing_conditions"][:120] or "Tow if unsafe.",
                }
            return out
        if request.tool_name == "merge_questions":
            # Merge questions with identical text (case-insensitive); keep option labels as they are.
            groups: dict[str, dict] = {}
            for q in ctx["questions"]:
                g = groups.setdefault(q["text"].lower(), {"canonical_text": q["text"], "question_ids": [], "opts": {}})
                g["question_ids"].append(q["id"])
                for o in q["options"]:
                    g["opts"].setdefault(o["label"].lower(), {"label": o["label"], "option_refs": []})
                    g["opts"][o["label"].lower()]["option_refs"].append(o["ref"])
            return {
                "groups": [
                    {
                        "canonical_text": g["canonical_text"],
                        "question_ids": g["question_ids"],
                        "options": list(g["opts"].values()),
                    }
                    for g in groups.values()
                ]
            }
        raise LLMError(f"fake provider has no answer for {request.tool_name}")


PROVIDERS = ("anthropic", "openai", "fake")


def make_provider(name: str, settings: Any, model: str = "", effort: str = "") -> LLMProvider:
    """Build the provider named by --provider or LLM_PROVIDER. model / effort override the settings."""
    if name == "anthropic":
        return AnthropicProvider(
            model=model or settings.questions_model,
            effort=effort or settings.questions_effort,
            api_key=settings.anthropic_api_key,
        )
    if name == "openai":
        prices = (
            settings.openai_price_input_per_m,
            settings.openai_price_output_per_m,
            settings.openai_price_cached_input_per_m,
            settings.openai_price_input_per_m,
        )
        return OpenAIProvider(
            model=model or settings.openai_model,
            api_key=settings.openai_api_key,
            reasoning_effort=effort or settings.openai_reasoning_effort,
            prices=prices if prices[0] and prices[1] else None,
        )
    if name == "fake":
        return FakeProvider(model="fake")
    raise LLMError(f"unknown LLM provider '{name}' (use one of: {', '.join(PROVIDERS)})")
