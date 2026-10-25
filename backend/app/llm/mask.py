"""Mask personal data before any text is sent to an LLM: emails, phone numbers and vehicle registration
numbers become placeholders. The diagnosis never needs them."""

import re
from dataclasses import dataclass, field

EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
# Indian state / UT codes used on number plates.
STATES = (
    "AN|AP|AR|AS|BR|CG|CH|DD|DL|DN|GA|GJ|HP|HR|JH|JK|KA|KL|LA|LD|MH|ML|MN|MP|MZ|NL|OD|OR|PB|PY|RJ|SK|TN|TR|TS|UK|UP|WB"
)
SEP = r"[\s.-]?"
# State code, district number (DL also adds a letter: DL 3C), up to two letter groups, four digits.
# Also the BH (Bharat) series: 22 BH 1234 AB.
REGISTRATION = re.compile(
    rf"(?<![a-z0-9])(?:(?:{STATES}){SEP}\d{{1,2}}{SEP}(?:[a-z]{{1,3}}{SEP}){{0,2}}\d{{4}}"
    rf"|\d{{2}}{SEP}bh{SEP}\d{{4}}{SEP}[a-z]{{1,2}})(?![a-z0-9])",
    re.IGNORECASE,
)
# Indian mobiles (+91 / 0 prefix optional, spaces or dashes inside), and any other run of 10-13 digits.
PHONE = re.compile(r"(?<![\w+])(?:\+?91[\s.-]*|0)?[6-9](?:[\s.-]*\d){9}(?!\d)|(?<!\d)\+?\d(?:[\s.-]*\d){9,12}(?!\d)")
PLACEHOLDERS = {"email": "[EMAIL]", "vehicle_number": "[VEHICLE_NUMBER]", "phone": "[PHONE]"}


@dataclass
class Masked:
    text: str
    counts: dict[str, int] = field(default_factory=dict)  # kind -> how many were masked


def mask(text: str) -> Masked:
    """Emails first (they can contain digits), then number plates, then phone numbers."""
    counts: dict[str, int] = {}
    for kind, pattern in (("email", EMAIL), ("vehicle_number", REGISTRATION), ("phone", PHONE)):
        text, n = pattern.subn(PLACEHOLDERS[kind], text)
        if n:
            counts[kind] = n
    return Masked(text, counts)
