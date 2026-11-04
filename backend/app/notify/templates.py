"""Message templates in English and Hindi: short and plain. The same wording is registered as the WhatsApp templates
and the DLT SMS templates (docs/notifications-setup.md lists them with their variables), so what the console prints
is what a customer or mechanic receives.

Values come from the request and are cleaned first (clean_value): phone numbers are removed and lengths capped, so a
customer's message can never carry the mechanic's number, nor a mechanic's message the customer's (customers type
free text into the area, notes and problem fields). Customers see the mechanic's first name only.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.llm.mask import PHONE

BRAND = "Instant Mechanic"
LANGUAGES = ("en", "hi")
MAX_VALUE = 60  # WhatsApp allows more; short values keep messages readable
SMS_MAX_VALUE = 30  # DLT {#var#} values are limited to 30 characters


@dataclass(frozen=True)
class Template:
    key: str
    # The values the text uses, in order: WhatsApp body {{1}}, {{2}} ... and DLT {#var#} 1, 2 ...
    variables: tuple[str, ...]
    text: dict[str, str]  # language -> text (WhatsApp, push and the console)
    sms: dict[str, str] = field(default_factory=dict)  # a different SMS text (no buttons in SMS), else `text`
    buttons: tuple[tuple[str, dict[str, str]], ...] = ()  # (payload action, {language: label}) quick replies
    title: dict[str, str] = field(default_factory=lambda: {"en": BRAND, "hi": BRAND})  # push notification title


TEMPLATES: dict[str, Template] = {
    t.key: t
    for t in (
        Template(
            "job_offer",
            ("reference", "problem", "area", "car"),
            {
                "en": "New job {reference}: {problem}. Area: {area}. Car: {car}. Tap Accept or Reject.",
                "hi": "नया काम {reference}: {problem}. जगह: {area}. गाड़ी: {car}. Accept या Reject दबाएँ।",
            },
            sms={
                "en": "New job {reference}: {problem}. Area: {area}. Car: {car}. "
                "Call Instant Mechanic support to accept. -Instant Mechanic",
                "hi": "नया काम {reference}: {problem}. जगह: {area}. गाड़ी: {car}. "
                "काम लेने के लिए Instant Mechanic सपोर्ट को कॉल करें। -Instant Mechanic",
            },
            buttons=(("accept", {"en": "Accept", "hi": "Accept"}), ("reject", {"en": "Reject", "hi": "Reject"})),
        ),
        Template(
            "mechanic_assigned",
            ("mechanic", "reference"),
            {
                "en": "Instant Mechanic: {mechanic} will fix your car ({reference}). "
                "We will tell you when they are on the way.",
                "hi": "Instant Mechanic: {mechanic} आपकी गाड़ी ठीक करेंगे ({reference})। रास्ते में होने पर हम आपको बताएँगे।",
            },
        ),
        Template(
            "mechanic_en_route",
            ("mechanic", "reference"),
            {
                "en": "Instant Mechanic: {mechanic} is on the way to you ({reference}).",
                "hi": "Instant Mechanic: {mechanic} आपके पास आ रहे हैं ({reference})।",
            },
        ),
        Template(
            "mechanic_arrived",
            ("mechanic", "reference"),
            {
                "en": "Instant Mechanic: {mechanic} has arrived ({reference}).",
                "hi": "Instant Mechanic: {mechanic} पहुँच गए हैं ({reference})।",
            },
        ),
        Template(
            "job_completed",
            ("reference",),
            {
                "en": "Instant Mechanic: your job {reference} is done. Thank you for choosing us.",
                "hi": "Instant Mechanic: आपका काम {reference} पूरा हो गया। हमें चुनने के लिए धन्यवाद।",
            },
        ),
        # Replies on WhatsApp right after the person wrote to us (inside WhatsApp's 24-hour window: plain text, no
        # approved template needed).
        Template(
            "offer_accepted_ack",
            ("reference",),
            {
                "en": "Thanks! Job {reference} is yours. Our team will call you with the details.",
                "hi": "धन्यवाद! काम {reference} आपका है। हमारी टीम आपको पूरी जानकारी के लिए कॉल करेगी।",
            },
        ),
        Template(
            "offer_declined_ack",
            ("reference",),
            {
                "en": "Okay, we have noted that you cannot take job {reference}.",
                "hi": "ठीक है, हमने नोट कर लिया कि आप काम {reference} नहीं ले सकते।",
            },
        ),
        Template(
            "offer_closed",
            ("reference",),
            {
                "en": "Job {reference} is no longer open, so nothing has changed.",
                "hi": "काम {reference} अब खुला नहीं है, इसलिए कुछ नहीं बदला।",
            },
        ),
        Template(
            "whatsapp_stopped",
            (),
            {
                "en": "You will not get WhatsApp messages from Instant Mechanic now. Send START to turn them on again.",
                "hi": "अब आपको Instant Mechanic से WhatsApp संदेश नहीं मिलेंगे। फिर से चालू करने के लिए START भेजें।",
            },
        ),
        Template(
            "whatsapp_started",
            (),
            {
                "en": "You will now get updates from Instant Mechanic on WhatsApp. Send STOP to turn them off.",
                "hi": "अब आपको Instant Mechanic से WhatsApp पर अपडेट मिलेंगे। बंद करने के लिए STOP भेजें।",
            },
        ),
    )
}
# Sent on WhatsApp as approved templates (business-initiated); the rest are replies inside the 24-hour window.
WHATSAPP_TEMPLATE_SETTING = {
    "job_offer": "whatsapp_tpl_job_offer",
    "mechanic_assigned": "whatsapp_tpl_mechanic_assigned",
    "mechanic_en_route": "whatsapp_tpl_mechanic_en_route",
    "mechanic_arrived": "whatsapp_tpl_mechanic_arrived",
    "job_completed": "whatsapp_tpl_job_completed",
}
SESSION_REPLIES = {"offer_accepted_ack", "offer_declined_ack", "offer_closed", "whatsapp_stopped", "whatsapp_started"}


def sms_template_setting(template: str, language: str) -> str:
    """The Settings field with the MSG91 template id of this SMS (e.g. msg91_tpl_job_offer_hi)."""
    return f"msg91_tpl_{template}_{language}"


_SPACE = re.compile(r"\s+")


def clean_value(value: object, limit: int = MAX_VALUE) -> str:
    """One line, phone numbers removed, at most `limit` characters (WhatsApp refuses new lines and tabs in values)."""
    text = _SPACE.sub(" ", PHONE.sub("[number removed]", str(value or ""))).strip()
    if len(text) > limit:
        text = text[: limit - 1].rstrip() + "…"
    return text or "-"


@dataclass
class Rendered:
    title: str
    text: str
    values: list[str]  # in `variables` order (WhatsApp / SMS parameters)
    buttons: list[tuple[str, str]]  # (action, label)


def render(key: str, language: str, params: dict, *, sms: bool = False) -> Rendered:
    t = TEMPLATES[key]
    lang = language if language in t.text else "en"
    limit = SMS_MAX_VALUE if sms else MAX_VALUE
    values = {v: clean_value(params.get(v), limit) for v in t.variables}
    body = (t.sms if sms and t.sms else t.text)[lang]
    return Rendered(
        title=t.title.get(lang, BRAND),
        text=body.format(**values),
        values=[values[v] for v in t.variables],
        buttons=[(action, labels.get(lang, labels["en"])) for action, labels in t.buttons],
    )


def language_of(detected: str | None) -> str:
    """The diagnosis's detected language -> template language: Hindi for Devanagari or Hinglish, else English."""
    return "hi" if detected in ("hi", "hinglish") else "en"


def registration_text(key: str, language: str, kind: str) -> str:
    """The template as it is registered: WhatsApp bodies number their values {{1}}, {{2}} ...; DLT SMS templates
    mark each value {#var#}. Used to write docs/notifications-setup.md (python -m app.notify.templates)."""
    t = TEMPLATES[key]
    body = (t.sms if kind == "sms" and t.sms else t.text)[language]
    marks = {v: ("{#var#}" if kind == "sms" else f"{{{{{i}}}}}") for i, v in enumerate(t.variables, start=1)}
    return body.format(**marks)


if __name__ == "__main__":
    for key in WHATSAPP_TEMPLATE_SETTING:
        t = TEMPLATES[key]
        print(f"## {key}  (values: {', '.join(t.variables)})")
        for lang in LANGUAGES:
            print(f"WhatsApp {lang}: {registration_text(key, lang, 'whatsapp')}")
            if t.buttons:
                print(f"  quick replies: {', '.join(labels[lang] for _, labels in t.buttons)}")
            print(f"SMS {lang}:      {registration_text(key, lang, 'sms')}")
        print()
