import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class OtpRequestIn(BaseModel):
    phone: str = Field(description="Indian mobile number, 10 digits (with or without +91).", examples=["9876543210"])


class OtpRequestOut(BaseModel):
    sent: bool = True
    phone_masked: str = Field(examples=["+91******3210"])
    expires_in: int = Field(description="Seconds the code is valid.")


class OtpVerifyIn(BaseModel):
    phone: str
    code: str = Field(examples=["123456"])
    consent: bool = Field(description="The customer ticked the consent box (GET /api/auth/config).")
    consent_text_version: str = Field(examples=["account-v1"])


class AuthConfigOut(BaseModel):
    consent_version: str
    consent_text: str
    code_length: int = 6
    expires_in: int


class UserOut(BaseModel):
    id: uuid.UUID
    phone_masked: str
    name: str | None
    created_at: datetime


class LoginOut(BaseModel):
    user: UserOut
    attached: dict = Field(description="Diagnosis sessions and requests from this browser now in the account.")


class MeOut(BaseModel):
    user: UserOut
    vehicles: int
    sessions: int
    requests: int


class VehicleOut(BaseModel):
    id: int
    label: str
    variant_id: int | None
    created_at: datetime


class SessionSummaryOut(BaseModel):
    session_id: uuid.UUID
    created_at: datetime
    status: str
    vehicle: str
    topic: str | None
    top_cause: str | None


class RequestSummaryOut(BaseModel):
    id: uuid.UUID
    reference: str
    created_at: datetime
    status: str
    status_label: str
    urgent: bool
    vehicle: str
    problem_summary: str


class TimelineStep(BaseModel):
    key: str
    label: str
    state: Literal["done", "current", "upcoming", "cancelled"]
    at: datetime | None = None


class RequestDetailOut(RequestSummaryOut):
    service_type: str
    area: str
    preferred_time: str
    session_id: uuid.UUID | None
    timeline: list[TimelineStep]


class DeleteAccountIn(BaseModel):
    confirm: Literal["DELETE"] = Field(description='Type "DELETE" to confirm.')


class DeleteAccountOut(BaseModel):
    deleted: bool = True
    sessions: int
    requests: int
    vehicles: int
