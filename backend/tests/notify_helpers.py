"""Fake notification channels and a synchronous stand-in for the worker (no Redis, no providers)."""

from __future__ import annotations

from app.notify import inbound
from app.notify import service as notify
from app.notify.channels import Message, SendFailed
from app.notify.models import Channel
from app.notify.queue import INBOUND_FUNCTION, SEND_FUNCTION, RecordingQueue


class FakeChannel:
    """Records what it sends. `script`: results for the next sends, in order: "ok", "retry" (a temporary error),
    "fail" (a permanent error); afterwards every send succeeds. `unavailable_reason`: pretend it is not configured."""

    def __init__(self, name: str = "fake", script: list[str] | None = None, unavailable_reason: str | None = None):
        self.name = name
        self.script = list(script or [])
        self.unavailable_reason = unavailable_reason
        self.sent: list[Message] = []
        self.calls = 0

    def unavailable(self, msg: Message) -> str | None:
        return self.unavailable_reason

    def send(self, msg: Message) -> str | None:
        self.calls += 1
        outcome = self.script.pop(0) if self.script else "ok"
        if outcome == "retry":
            raise SendFailed("provider timed out", retry=True)
        if outcome == "fail":
            raise SendFailed("provider refused the message", retry=False)
        msg.sent_language = msg.language
        self.sent.append(msg)
        return f"{self.name}-id-{len(self.sent)}"


def fake_channels(**overrides: FakeChannel) -> dict[Channel, FakeChannel]:
    chans = {c: FakeChannel(f"fake-{c.value}") for c in Channel}
    chans.update({Channel(k): v for k, v in overrides.items()})
    return chans


def drain(session, queue: RecordingQueue, channels, settings, limit: int = 100) -> list[str]:
    """Run every queued job the way the worker does (one transaction each), until nothing is left."""
    outcomes = []
    for _ in range(limit):
        if not queue.jobs:
            return outcomes
        function, arg, _job_id, _when = queue.jobs.pop(0)
        if function == SEND_FUNCTION:
            outcomes.append(notify.send(session, channels, settings, arg))
        elif function == INBOUND_FUNCTION:
            outcomes.append(inbound.handle(session, settings, arg))
        session.commit()
    raise AssertionError(f"the queue did not drain: {queue.jobs[:5]}")
