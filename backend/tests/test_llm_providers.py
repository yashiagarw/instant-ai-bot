"""Provider selection and the OpenAI provider, with stubbed clients (no network, no API keys)."""

import copy
import json
from argparse import Namespace
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.config import Settings
from app.knowledge.questions import prompts as PR
from app.knowledge.questions.__main__ import cmd_generate, provider_name
from app.knowledge.questions.generate import generate_category
from app.knowledge.questions.llm import (
    AnthropicProvider,
    FakeProvider,
    LLMError,
    OpenAIProvider,
    ToolRequest,
    Usage,
    check_schema,
    make_provider,
)
from tests.test_questions import DATASET, make_inputs


def settings(**overrides) -> Settings:
    base = dict(anthropic_api_key="test-anthropic", openai_api_key="test-openai", openai_model="test-openai-model")
    return Settings(_env_file=None, **{**base, **overrides})


# ---------------------------------------------------------------- selection


def test_llm_provider_setting_reads_environment(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_MODEL", "some-model")
    s = Settings(_env_file=None)
    assert s.llm_provider == "openai" and s.openai_model == "some-model"


def test_llm_provider_defaults_to_none(monkeypatch):
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    assert Settings(_env_file=None).llm_provider == "none"


def test_offline_generation_needs_a_real_provider_when_the_setting_is_none():
    s = settings(llm_provider="none")
    assert provider_name(Namespace(provider=None), s) == "none"
    with pytest.raises(LLMError, match="LLM_PROVIDER is none"):
        make_provider("none", s)


def test_llm_provider_rejects_unknown_values(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_make_provider_anthropic():
    p = make_provider("anthropic", settings())
    assert isinstance(p, AnthropicProvider) and p.name == "anthropic"
    assert p.model == "claude-opus-5-5" and p.effort == "high"


def test_make_provider_openai_uses_its_own_settings():
    p = make_provider("openai", settings(openai_reasoning_effort="medium"))
    assert isinstance(p, OpenAIProvider) and p.name == "openai"
    assert p.model == "test-openai-model" and p.effort == "medium"
    assert p.usage.prices is None  # no prices configured -> cost not estimated


def test_make_provider_overrides_and_prices():
    s = settings(openai_price_input_per_m=1.0, openai_price_cached_input_per_m=0.1, openai_price_output_per_m=4.0)
    p = make_provider("openai", s, model="other-model", effort="low")
    assert (p.model, p.effort) == ("other-model", "low")
    assert p.usage.prices == (1.0, 4.0, 0.1, 1.0)


def test_make_provider_openai_requires_a_model():
    with pytest.raises(LLMError, match="OPENAI_MODEL"):
        make_provider("openai", settings(openai_model=""))


def test_make_provider_fake_and_unknown():
    assert isinstance(make_provider("fake", settings()), FakeProvider)
    with pytest.raises(LLMError, match="unknown LLM provider"):
        make_provider("gemini", settings())


def test_cli_flag_beats_setting():
    s = settings(llm_provider="openai")
    assert provider_name(Namespace(provider=None), s) == "openai"
    assert provider_name(Namespace(provider="anthropic"), s) == "anthropic"
    assert provider_name(Namespace(provider="fake"), s) == "fake"


def test_generate_stops_cleanly_when_openai_model_missing(monkeypatch, capsys):
    monkeypatch.setattr(
        "app.knowledge.questions.__main__.get_settings", lambda: settings(llm_provider="openai", openai_model="")
    )
    args = Namespace(phase1=False, category=["battery"], provider=None, model=None, effort=None, workers=1)
    assert cmd_generate(args, session=None) == 2  # stops before touching the database or any API
    assert "OPENAI_MODEL" in capsys.readouterr().err


# ---------------------------------------------------------------- OpenAI request and response handling


def oa_response(
    text="", status="completed", reason=None, refusal=None, input_tokens=1200, cached=800, written=0, output_tokens=300
):
    content = (
        [SimpleNamespace(type="refusal", refusal=refusal)]
        if refusal
        else [SimpleNamespace(type="output_text", text=text)]
    )
    usage = SimpleNamespace(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        input_tokens_details=SimpleNamespace(cached_tokens=cached, cache_write_tokens=written),
    )
    return SimpleNamespace(
        status=status,
        incomplete_details=SimpleNamespace(reason=reason) if reason else None,
        output=[SimpleNamespace(type="message", content=content)],
        output_text="" if refusal else text,
        usage=usage,
        model="test-openai-model",
    )


class StubResponses:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(copy.deepcopy(kwargs))
        return self.responses.pop(0)


def openai_with(responses, **kw) -> tuple[OpenAIProvider, StubResponses]:
    p = OpenAIProvider(model="test-openai-model", api_key="test-openai", **kw)
    stub = StubResponses(responses)
    p.client = SimpleNamespace(responses=stub)
    return p, stub


SCHEMA = PR.fault_schema(["Car not starting", "Self slow"], draft_safety=False)
VALID = {
    "stage2_choices": ["Self slow"],
    "follow_up_questions": [
        {
            "text": "Q?",
            "source": "symptoms",
            "options": [{"label": "Yes", "effect": "supports", "strength": "strong", "safety_trigger": False}],
        }
    ],
    "confirmation_test": "Battery test.",
    "danger_phrases": [],
}
REQ = ToolRequest("structure_fault", "Structure one fault.", SCHEMA, "static text", "category text", "fault text", {})


def test_openai_request_uses_the_same_strict_schema():
    p, stub = openai_with([oa_response(json.dumps(VALID))])
    assert p.call(REQ) == VALID
    kw = stub.calls[0]
    fmt = kw["text"]["format"]
    assert fmt == {
        "type": "json_schema",
        "name": "structure_fault",
        "description": "Structure one fault.",
        "schema": SCHEMA,
        "strict": True,
    }
    assert kw["instructions"] == "static text\n\ncategory text"
    assert kw["input"] == [{"role": "user", "content": "fault text"}]
    assert kw["store"] is False and kw["max_output_tokens"] == 16000
    assert kw["prompt_cache_key"].startswith("autocare:structure_fault:")
    assert "temperature" not in kw and "reasoning" not in kw


def test_openai_reasoning_effort_sent_only_when_set():
    p, stub = openai_with([oa_response(json.dumps(VALID))], reasoning_effort="high")
    p.call(REQ)
    assert stub.calls[0]["reasoning"] == {"effort": "high"}


def test_openai_cache_key_is_stable_per_category():
    p, stub = openai_with([oa_response(json.dumps(VALID)), oa_response(json.dumps(VALID))])
    p.call(REQ)
    p.call(ToolRequest(REQ.tool_name, REQ.tool_description, SCHEMA, "static text", "category text", "other", {}))
    assert stub.calls[0]["prompt_cache_key"] == stub.calls[1]["prompt_cache_key"]


def test_openai_invalid_answer_is_retried_with_the_problem():
    bad = dict(VALID, stage2_choices=["Not a choice"])
    p, stub = openai_with([oa_response(json.dumps(bad)), oa_response(json.dumps(VALID))])
    assert p.call(REQ) == VALID
    retry = stub.calls[1]["input"]
    assert retry[1]["role"] == "assistant" and "not one of the allowed values" in retry[2]["content"]


def test_openai_gives_up_after_one_retry():
    p, _ = openai_with([oa_response("not json"), oa_response('{"still": "wrong"}')])
    with pytest.raises(LLMError, match="invalid JSON answer"):
        p.call(REQ)
    assert p.usage.calls == 2


@pytest.mark.parametrize(
    "response,match",
    [
        (lambda: oa_response(refusal="I can't help with that."), "refused"),
        (lambda: oa_response(status="incomplete", reason="max_output_tokens"), "incomplete"),
        (lambda: oa_response(status="incomplete", reason="content_filter"), "content filter"),
        (lambda: oa_response(status="failed"), "status failed"),
    ],
)
def test_openai_refusal_truncation_and_failure(response, match):
    p, _ = openai_with([response()])
    with pytest.raises(LLMError, match=match):
        p.call(REQ)


def openai_usage_after(*responses, **price_settings):
    p = make_provider("openai", settings(**price_settings))
    p.client = SimpleNamespace(responses=StubResponses([oa_response(json.dumps(VALID), **r) for r in responses]))
    for _ in responses:
        p.call(REQ)
    return p.usage.as_dict(p.model)


def test_openai_usage_mapping():
    """input_tokens as reported, cached from input_tokens_details.cached_tokens, never any cache writes."""
    d = openai_usage_after(dict(input_tokens=1200, cached=800, written=100, output_tokens=300))
    assert (d["input_tokens"], d["cache_read_input_tokens"], d["cache_creation_input_tokens"]) == (1200, 800, 0)
    assert d["output_tokens"] == 300 and d["calls"] == 1 and d["served_by"] == ["test-openai-model"]


def test_openai_usage_for_the_tyre_run_numbers():
    """The real tyre run reported 21,342 input tokens and cache_write_tokens 21,318 (logged wrongly as 24 input)."""
    d = openai_usage_after(dict(input_tokens=21342, cached=0, written=21318, output_tokens=16671))
    assert (d["input_tokens"], d["cache_read_input_tokens"], d["cache_creation_input_tokens"]) == (21342, 0, 0)


def test_openai_usage_accumulates_across_calls():
    d = openai_usage_after(
        dict(input_tokens=1000, cached=0, output_tokens=100), dict(input_tokens=1000, cached=900, output_tokens=100)
    )
    assert (d["calls"], d["input_tokens"], d["cache_read_input_tokens"], d["output_tokens"]) == (2, 2000, 900, 200)


def test_openai_cost_counts_cached_tokens_once():
    d = openai_usage_after(
        dict(input_tokens=1200, cached=800, written=100, output_tokens=300),
        openai_price_input_per_m=1.0,
        openai_price_cached_input_per_m=0.1,
        openai_price_output_per_m=4.0,
    )
    # 400 uncached at 1.0 + 800 cached at 0.1 + 300 output at 4.0; nothing for cache writes.
    assert d["cost_usd_estimate"] == round((400 * 1.0 + 800 * 0.1 + 300 * 4.0) / 1e6, 4)


def test_anthropic_usage_unchanged():
    """Claude reports uncached input separately, so its cost adds the parts as before."""
    u = Usage()
    u.add(
        SimpleNamespace(
            input_tokens=400, output_tokens=300, cache_read_input_tokens=800, cache_creation_input_tokens=100
        ),
        "claude-opus-5-5",
        False,
    )
    assert u.cost_usd("claude-opus-5-5") == round((400 * 4 + 300 * 20 + 800 * 0.2 + 100 * 5) / 1e6, 4)


def test_cost_unknown_without_prices():
    u = Usage()
    u.add_counts("some-openai-model", 1000, 100)
    assert u.as_dict("some-openai-model")["cost_usd_estimate"] is None


# ---------------------------------------------------------------- schema check and end-to-end


def test_check_schema_matches_the_strict_subset():
    check_schema(VALID, SCHEMA)
    for broken in (
        {k: v for k, v in VALID.items() if k != "confirmation_test"},  # missing required
        dict(VALID, extra=1),  # additionalProperties false
        dict(VALID, danger_phrases="smoke"),  # wrong type
        dict(VALID, follow_up_questions=[dict(VALID["follow_up_questions"][0], source="guess")]),  # enum
    ):
        with pytest.raises(LLMError):
            check_schema(broken, SCHEMA)


class OpenAIBackedByFake(OpenAIProvider):
    """Real OpenAIProvider parsing/validation; the 'API' answers with FakeProvider's output as JSON text."""

    def __init__(self):
        super().__init__(model="test-openai-model", api_key="test-openai")
        self._fake = FakeProvider()

    def _create(self, request, extra_input):
        return oa_response(json.dumps(self._fake.call(request)))


def test_generator_runs_on_the_openai_provider_with_the_same_schemas():
    provider = OpenAIBackedByFake()
    doc = generate_category(make_inputs(), provider, DATASET, workers=2, log=lambda _: None)
    assert doc["generated"]["provider"] == "openai" and doc["generated"]["model"] == "test-openai-model"
    assert [o["label"] for o in doc["questions"][0]["options"]] == [
        "Car not starting",
        "Self slow",
        "Other",
        "Not sure",
    ]
    assert len(doc["safety_rules"]) == 3
    assert provider.usage.calls == 4  # 3 faults + 1 merge, every answer schema-checked


def test_images_go_before_the_text_as_base64_blocks():
    from app.llm.providers import LLMRequest, ToolSpec, _content

    tool = ToolSpec("t", "d", {"type": "object"})
    assert _content(LLMRequest("m", "s", "hello", tool, 10)) == "hello"
    blocks = _content(LLMRequest("m", "s", "what light?", tool, 10, images=[("image/jpeg", b"\xff\xd8\xff")]))
    assert blocks[0] == {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": "/9j/"}}
    assert blocks[-1] == {"type": "text", "text": "what light?"}
