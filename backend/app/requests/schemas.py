"""Request a Mechanic: request and response schemas (shown in the OpenAPI docs)."""

import re
import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.requests.models import RequestStatus, ServiceType

MOBILE = re.compile(r"^(?:\+?91|0)?([6-9]\d{9})$")
PINCODE = re.compile(r"^[1-9]\d{5}$")

PREFERRED_TIMES = {
    "asap": "As soon as possible",
    "today": "Later today",
    "tomorrow_morning": "Tomorrow morning",
    "tomorrow_evening": "Tomorrow evening",
}


def normalise_mobile(value: str) -> str:
    """+91 and ten digits, from "98765 43210", "+91-98765-43210", "098765 43210" and the like."""
    digits = re.sub(r"[\s().-]", "", value or "")
    m = MOBILE.match(digits)
    if not m:
        raise ValueError("enter a 10-digit Indian mobile number starting with 6, 7, 8 or 9")
    return f"+91{m.group(1)}"


class PreferredTimeOut(BaseModel):
    value: str
    label: str


class RequestConfigOut(BaseModel):
    consent_version: str = Field(description="Send back as `consent_text_version`.")
    consent_text: str = Field(description="Show this wording next to the (unticked) consent checkbox.")
    helpline_number: str = Field(description="Shown as text. Empty when not configured.")
    preferred_times: list[PreferredTimeOut]
    whatsapp_consent_version: str = Field(description="Send back as `whatsapp_consent_version` when ticked.")
    whatsapp_consent_text: str = Field(description="The optional WhatsApp updates box (unticked by default).")


class ServiceRequestIn(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {
                    "session_id": "6a30a194-9887-4319-8dea-f0b92584c45f",
                    "name": "Asha",
                    "phone": "98765 43210",
                    "service_type": "at_location",
                    "area": "Sector 62, Noida",
                    "pincode": "201309",
                    "preferred_time": "asap",
                    "consent": True,
                    "consent_text_version": "request-v1",
                }
            ]
        },
    )

    session_id: uuid.UUID | None = Field(default=None, description="The diagnosis this request is about.")
    name: str = Field(min_length=2, max_length=80)
    phone: str = Field(description="Indian mobile number; stored as +91 and 10 digits.", examples=["98765 43210"])
    service_type: ServiceType = Field(description="at_location (mechanic comes to you), tow, or workshop visit.")
    area: str = Field(min_length=2, max_length=120, description="Area, sector or landmark.")
    pincode: str = Field(default="", description="6 digits. Optional for urgent requests.")
    address: str = Field(default="", max_length=300)
    preferred_time: str = Field(default="", description="One of the values from GET /api/service-requests/config.")
    notes: str = Field(default="", max_length=500)
    consent: bool = Field(description="Must be true: the customer ticked the consent box.")
    consent_text_version: str = Field(min_length=1, max_length=40)
    whatsapp_optin: bool = Field(
        default=False, description="The customer ticked the separate, optional WhatsApp updates box."
    )
    whatsapp_consent_version: str | None = Field(
        default=None, max_length=40, description="The WhatsApp wording version shown (GET /config), when ticked."
    )
    language: Literal["en", "hi"] | None = Field(
        default=None,
        description="The language the customer used on the site; notifications about this request use it. "
        "Omitted: detected from what the customer typed.",
    )

    @field_validator("name", "area", "address", "notes", "pincode")
    @classmethod
    def strip(cls, v: str) -> str:
        return v.strip()

    @field_validator("phone")
    @classmethod
    def mobile(cls, v: str) -> str:
        return normalise_mobile(v)

    @field_validator("pincode")
    @classmethod
    def valid_pincode(cls, v: str) -> str:
        if v and not PINCODE.match(v):
            raise ValueError("enter a 6-digit pincode")
        return v

    @field_validator("preferred_time")
    @classmethod
    def time(cls, v: str) -> str:
        if v and v not in PREFERRED_TIMES:
            raise ValueError(f"preferred_time must be one of {sorted(PREFERRED_TIMES)}")
        return v

    @field_validator("consent")
    @classmethod
    def consented(cls, v: bool) -> bool:
        if v is not True:
            raise ValueError("consent is required to send your details to the team")
        return v


class ServiceRequestOut(BaseModel):
    id: uuid.UUID = Field(description="For the live tracking page (/track/{id}), open to this browser and the account")
    reference: str = Field(examples=["IM-7K3Q9P"])
    status: RequestStatus
    urgent: bool
    created_at: datetime
    helpline_number: str
    next_steps: list[str]
