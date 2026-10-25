"""LLMClient: runs one provider call with a wall-clock timeout and the daily spend cap, validates the output,
and logs every call. Any failure returns `used=False` so the caller takes its non-LLM fallback; nothing here
raises into the request.

make_llm_client() returns None unless LLM_PROVIDER=anthropic and ANTHROPIC_API_KEY are set: then every LLM step
uses its fallback and no call is made.
"""

from __future__ import annotations

import logging
import threading
import time
import uuid
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from contextlib import AbstractContextManager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from datetime import time as dtime
from decimal import Decimal
from typing import Any, Protocol
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.llm.models import LLMCall, LLMOutcome
from app.llm.pricing import estimate_cost, has_price
from app.llm.providers import LLMError, LLMProvider, LLMRequest, LLMResponse, ToolSpec

log = logging.getLogger(__name__)
SPEND_DAY_TZ = ZoneInfo("Asia/Kolkata")  # the spend cap resets at midnight India time


class OutputError(ValueError):
    """The model's tool input has the wrong shape (the caller's validator raises it)."""


# validate(tool input) -> (value to use, number of items dropped). Raises OutputError for unusable output.
Validator = Callable[[dict], tuple[Any, int]]


@dataclass
class CallRecord:
    purpose: str
    provider: str
    model: str
    prompt_version: str
    outcome: str
    session_id: uuid.UUID | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    latency_ms: int = 0
    cost_usd: float = 0.0
    detail: str = ""


class Recorder(Protocol):
    def record(self, rec: CallRecord) -> None: ...

    def spent_today(self) -> float: ...


def day_start(now: datetime | None = None) -> datetime:
    """Midnight today, India time, as an aware datetime."""
    local = (now or datetime.now(UTC)).astimezone(SPEND_DAY_TZ)
    return datetime.combine(local.date(), dtime(0), tzinfo=SPEND_DAY_TZ)


class DbRecorder:
    """Writes llm_calls rows. `connect()` yields a Session in its own transaction (sessionmaker.begin), so a
    log row survives a failed request and can be written from the thread of a call that timed out."""

    def __init__(self, connect: Callable[[], AbstractContextManager[Session]]):
        self.connect = connect

    def record(self, rec: CallRecord) -> None:
        with self.connect() as s:
            s.add(
                LLMCall(
                    session_id=rec.session_id,
                    purpose=rec.purpose,
                    provider=rec.provider,
                    model=rec.model,
                    prompt_version=rec.prompt_version,
                    input_tokens=rec.input_tokens,
                    output_tokens=rec.output_tokens,
                    cache_read_tokens=rec.cache_read_tokens,
                    cache_write_tokens=rec.cache_write_tokens,
                    latency_ms=rec.latency_ms,
                    cost_usd=Decimal(str(rec.cost_usd)),
                    outcome=rec.outcome,
                    detail=rec.detail,
                )
            )
            s.flush()

    def spent_today(self) -> float:
        with self.connect() as s:
            total = s.scalar(
                select(func.coalesce(func.sum(LLMCall.cost_usd), 0)).where(LLMCall.created_at >= day_start())
            )
        return float(total or 0)


@dataclass
class MemoryRecorder:
    """In-memory log (tests, the evaluation harness)."""

    records: list[CallRecord] = field(default_factory=list)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def record(self, rec: CallRecord) -> None:
        with self._lock:
            self.records.append(rec)

    def spent_today(self) -> float:
        with self._lock:
            return sum(r.cost_usd for r in self.records)

    def summary(self) -> dict:
        with self._lock:
            out: dict[str, Any] = {"calls": len(self.records), "outcomes": {}}
            for r in self.records:
                out["outcomes"][r.outcome] = out["outcomes"].get(r.outcome, 0) + 1
            out["input_tokens"] = sum(r.input_tokens for r in self.records)
            out["output_tokens"] = sum(r.output_tokens for r in self.records)
            out["cost_usd_estimate"] = round(sum(r.cost_usd for r in self.records), 4)
            return out


@dataclass
class Outcome:
    value: Any  # the validated output, or None when the fallback must be used
    used: bool
    outcome: str


class LLMClient:
    def __init__(
        self,
        provider: LLMProvider,
        recorder: Recorder,
        *,
        extraction_model: str,
        phrasing_model: str,
        explanation_model: str = "",
        effort: str = "low",
        timeout: float = 4.0,
        daily_cap_usd: float = 2.0,
        workers: int = 8,
    ):
        self.provider, self.recorder = provider, recorder
        self.models = {
            "extraction": extraction_model,
            "phrasing": phrasing_model,
            "explanation": explanation_model or phrasing_model,
        }
        self.effort, self.timeout, self.daily_cap_usd = effort, timeout, daily_cap_usd
        self._pool = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="llm")

    def _record(self, rec: CallRecord) -> None:
        try:
            self.recorder.record(rec)
        except Exception:  # logging must never break a diagnosis
            log.exception("could not log an LLM call")

    def _over_cap(self) -> bool:
        try:
            return self.recorder.spent_today() >= self.daily_cap_usd
        except Exception:  # cannot check the spend: do not call
            log.exception("could not read today's LLM spend")
            return True

    def run(
        self,
        purpose: str,
        prompt_version: str,
        system: str,
        user: str,
        tool: ToolSpec,
        max_tokens: int,
        validate: Validator,
        session_id: uuid.UUID | None = None,
        detail: str = "",
    ) -> Outcome:
        model = self.models[purpose]
        base = CallRecord(purpose, self.provider.name, model, prompt_version, "", session_id=session_id, detail=detail)

        def done(outcome: str, value: Any = None, **fields) -> Outcome:
            info = "; ".join(x for x in (base.detail, fields.pop("detail", "")) if x)
            self._record(CallRecord(**{**base.__dict__, **fields, "outcome": outcome, "detail": info}))
            used = outcome in (LLMOutcome.ok, LLMOutcome.dropped)
            return Outcome(value if used else None, used, outcome)

        if not has_price(model):
            return done(LLMOutcome.error, detail=f"no price for model {model} (app/llm/pricing.py)")
        if self._over_cap():
            return done(LLMOutcome.spend_cap, detail=f"daily cap ${self.daily_cap_usd}")

        request = LLMRequest(model, system, user, tool, max_tokens, self.effort)
        started = time.monotonic()
        future = self._pool.submit(self.provider.call, request)
        try:
            response: LLMResponse = future.result(timeout=self.timeout)
        except FutureTimeout:
            # The answer is no longer used. Log the row once the call ends, with the tokens it was billed.
            future.add_done_callback(lambda f: self._late(f, base, started))
            return Outcome(None, False, LLMOutcome.timeout)
        except LLMError as e:
            return done(LLMOutcome.error, latency_ms=_ms(started), detail=str(e)[:200])
        except Exception as e:  # an unexpected provider failure still falls back
            return done(LLMOutcome.error, latency_ms=_ms(started), detail=type(e).__name__)

        usage = _usage(response, model)
        if response.stop_reason == "refusal":
            return done(LLMOutcome.refused, **usage)
        if response.data is None:
            return done(LLMOutcome.invalid, detail=f"no tool call (stop: {response.stop_reason})", **usage)
        try:
            value, dropped = validate(response.data)
        except OutputError as e:
            return done(LLMOutcome.invalid, detail=str(e)[:200], **usage)
        if dropped:
            return done(LLMOutcome.dropped, value, detail=f"dropped {dropped}", **usage)
        return done(LLMOutcome.ok, value, **usage)

    def _late(self, future: Future, base: CallRecord, started: float) -> None:
        fields: dict = {"latency_ms": _ms(started)}
        exc = future.exception()
        if exc is None:
            fields |= _usage(future.result(), base.model)
        info = "; ".join(x for x in (base.detail, f"over {self.timeout}s", type(exc).__name__ if exc else "") if x)
        self._record(CallRecord(**{**base.__dict__, **fields, "outcome": LLMOutcome.timeout, "detail": info}))


def _ms(started: float) -> int:
    return round((time.monotonic() - started) * 1000)


def _usage(r: LLMResponse, model: str) -> dict:
    return {
        "input_tokens": r.input_tokens,
        "output_tokens": r.output_tokens,
        "cache_read_tokens": r.cache_read_tokens,
        "cache_write_tokens": r.cache_write_tokens,
        "cost_usd": estimate_cost(model, r.input_tokens, r.output_tokens, r.cache_read_tokens, r.cache_write_tokens),
    }


def make_llm_client(settings, recorder: Recorder) -> LLMClient | None:
    """The live client, or None (every LLM step then uses its fallback)."""
    if settings.llm_provider != "anthropic":
        return None
    if not settings.anthropic_api_key:
        log.warning("LLM_PROVIDER=anthropic but ANTHROPIC_API_KEY is empty: LLM steps use their fallbacks")
        return None
    from app.llm.providers import ClaudeProvider

    return LLMClient(
        ClaudeProvider(settings.anthropic_api_key, settings.llm_timeout_seconds),
        recorder,
        extraction_model=settings.llm_extraction_model,
        phrasing_model=settings.llm_phrasing_model,
        explanation_model=settings.llm_explanation_model,
        effort=settings.llm_effort,
        timeout=settings.llm_timeout_seconds,
        daily_cap_usd=settings.llm_daily_spend_cap_usd,
    )
