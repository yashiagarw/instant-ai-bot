"""One adapter per channel over the providers (email.py, sms.py, whatsapp.py, push.py), with the same two questions:

- unavailable(msg): why this channel cannot be used for this message right now (provider not configured, a template
  id missing, no address ...), or None. A reason makes the dispatcher log it and fall back to the next channel.
- send(msg): the provider's message id; raises SendFailed(retry=...) when it did not go out.

Console providers are the development default. In production they count as not configured (nothing would reach
anyone), except email, whose console provider was already allowed there.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Protocol

from app.config import Settings
from app.notify import templates as T
from app.notify.email import Email, EmailError, EmailSender, make_sender
from app.notify.models import Channel
from app.notify.push import ConsolePush, PushError, Target, WebPush
from app.notify.sms import ConsoleSms, SmsError, SmsSender, SmsSendError, make_sms
from app.notify.whatsapp import CloudWhatsapp, ConsoleWhatsapp, Outgoing, WhatsappError

log = logging.getLogger(__name__)


class SendFailed(Exception):
    def __init__(self, message: str, retry: bool):
        super().__init__(message)
        self.retry = retry


@dataclass
class Message:
    template: str
    language: str
    params: dict
    phone: str | None = None  # +91XXXXXXXXXX (never stored; resolved by the dispatcher at send time)
    email: Email | None = None
    push_targets: list[Target] = field(default_factory=list)
    url: str = ""  # opened when a push notification is tapped
    button_payloads: list[str] = field(default_factory=list)  # one per template button, in order
    gone: list[int] = field(default_factory=list)  # push subscriptions the push service says no longer exist
    sent_language: str = ""  # the language actually sent (a missing Hindi SMS template falls back to English)


class ChannelProvider(Protocol):
    name: str
    config_error: str | None  # why the provider cannot be used at all (missing credentials ...), or None

    def unavailable(self, msg: Message) -> str | None: ...

    def send(self, msg: Message) -> str | None: ...


def _console_in_production(settings: Settings, setting: str) -> str | None:
    if settings.environment == "production":
        return f"{setting}=console only prints messages: set a real provider (docs/notifications-setup.md)"
    return None


class EmailChannel:
    def __init__(self, settings: Settings, sender: EmailSender | None = None):
        self.settings, self._sender, self.config_error = settings, sender, None
        if sender is None:
            try:
                self._sender = make_sender(settings)
            except EmailError as e:
                self.config_error = str(e)
        self.name = settings.email_provider

    def unavailable(self, msg: Message) -> str | None:
        if self.config_error:
            return self.config_error
        if msg.email is None or not msg.email.to:
            return "SUPPORT_EMAIL is not set"
        return None

    def send(self, msg: Message) -> str | None:
        try:
            self._sender.send(msg.email)
        except EmailError as e:
            raise SendFailed(str(e)[:300], retry=True) from None
        msg.sent_language = "en"
        return None


class SmsChannel:
    def __init__(self, settings: Settings, sender: SmsSender | None = None):
        self.settings, self._sender, self.config_error = settings, sender, None
        if sender is None:
            try:
                self._sender = make_sms(settings)
            except SmsError as e:
                self.config_error = str(e)
        self.name = getattr(self._sender, "name", settings.sms_provider)

    def _template_id(self, template: str, language: str) -> str:
        return str(getattr(self.settings, T.sms_template_setting(template, language), "") or "")

    def _language(self, msg: Message) -> str | None:
        """The message's language if its template id is set, else English if that one is (None: neither)."""
        if isinstance(self._sender, ConsoleSms):
            return msg.language
        for lang in dict.fromkeys((msg.language, "en")):
            if self._template_id(msg.template, lang):
                return lang
        return None

    def unavailable(self, msg: Message) -> str | None:
        if self.config_error:
            return self.config_error
        if not msg.phone:
            return "no mobile number"
        if self._language(msg) is None:
            return f"{T.sms_template_setting(msg.template, msg.language).upper()} is not set (DLT template id)"
        return None

    def send(self, msg: Message) -> str | None:
        lang = self._language(msg) or "en"
        rendered = T.render(msg.template, lang, msg.params, sms=True)
        try:
            template_id = self._template_id(msg.template, lang)
            pid = self._sender.send_template(msg.phone, template_id, rendered.values, rendered.text)
        except SmsSendError as e:
            raise SendFailed(str(e), retry=e.retry) from None
        except SmsError as e:
            raise SendFailed(str(e), retry=False) from None
        msg.sent_language = lang
        return pid


class WhatsappChannel:
    def __init__(self, settings: Settings, client=None):
        self.settings, self._client, self.config_error = settings, client, None
        if client is None:
            if settings.whatsapp_provider == "cloud":
                try:
                    self._client = CloudWhatsapp(settings)
                except WhatsappError as e:
                    self.config_error = str(e)
            else:
                self.config_error = _console_in_production(settings, "WHATSAPP_PROVIDER")
                self._client = ConsoleWhatsapp()
        self.name = getattr(self._client, "name", settings.whatsapp_provider)

    def _template_name(self, template: str) -> str | None:
        setting = T.WHATSAPP_TEMPLATE_SETTING.get(template)
        if setting is None:
            return None  # a plain-text reply
        if isinstance(self._client, ConsoleWhatsapp):
            return getattr(self.settings, setting) or template
        return getattr(self.settings, setting) or ""

    def unavailable(self, msg: Message) -> str | None:
        if self.config_error:
            return self.config_error
        if not msg.phone:
            return "no mobile number"
        if self._template_name(msg.template) == "":
            return f"{T.WHATSAPP_TEMPLATE_SETTING[msg.template].upper()} is not set (approved template name)"
        return None

    def send(self, msg: Message) -> str | None:
        rendered = T.render(msg.template, msg.language, msg.params)
        buttons = [(p, label) for p, (_, label) in zip(msg.button_payloads, rendered.buttons, strict=False)]
        out = Outgoing(
            phone=msg.phone,
            text=rendered.text,
            template_name=self._template_name(msg.template),
            language=msg.language,
            values=rendered.values,
            buttons=buttons,
        )
        try:
            pid = self._client.send(out)
        except WhatsappError as e:
            raise SendFailed(str(e), retry=e.retry) from None
        msg.sent_language = msg.language
        return pid


class PushChannel:
    def __init__(self, settings: Settings, client=None):
        self.settings, self._client, self.config_error = settings, client, None
        if client is None:
            if settings.push_provider == "webpush":
                try:
                    self._client = WebPush(settings)
                except PushError as e:
                    self.config_error = str(e)
            else:
                self.config_error = _console_in_production(settings, "PUSH_PROVIDER")
                self._client = ConsolePush()
        self.name = getattr(self._client, "name", settings.push_provider)

    def unavailable(self, msg: Message) -> str | None:
        if self.config_error:
            return self.config_error
        if not msg.push_targets:
            return "no browser has alerts turned on"
        return None

    def send(self, msg: Message) -> str | None:
        rendered = T.render(msg.template, msg.language, msg.params)
        payload = {"title": rendered.title, "body": rendered.text, "url": msg.url, "tag": msg.params.get("reference")}
        ok, retry, errors = 0, False, []
        for target in msg.push_targets:
            try:
                self._client.send(target, payload)
                ok += 1
            except PushError as e:
                errors.append(str(e))
                retry = retry or e.retry
                if e.gone:
                    msg.gone.append(target.id)
        if ok == 0:
            raise SendFailed("; ".join(dict.fromkeys(errors))[:300], retry=retry)
        msg.sent_language = msg.language
        return f"{ok} of {len(msg.push_targets)} browsers"


def make_channels(settings: Settings) -> dict[Channel, ChannelProvider]:
    """The real channels from the settings (the worker builds them once)."""
    return {
        Channel.email: EmailChannel(settings),
        Channel.sms: SmsChannel(settings),
        Channel.whatsapp: WhatsappChannel(settings),
        Channel.push: PushChannel(settings),
    }
