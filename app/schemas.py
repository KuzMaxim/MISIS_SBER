from __future__ import annotations

from datetime import date
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.utils import ensure_hhmm


class OperationResponse(BaseModel):
    message: str
    data: dict[str, Any] = Field(default_factory=dict)


class MedicationCreate(BaseModel):
    user_id: str
    name: str
    schedule_times: list[str]
    course_days: int | None = Field(default=None, ge=1, le=365)
    started_at: date = Field(default_factory=date.today)
    note: str | None = None

    @field_validator("schedule_times")
    @classmethod
    def validate_schedule_times(cls, value: list[str]) -> list[str]:
        if not value:
            raise ValueError("Нужно указать хотя бы одно время напоминания")
        normalized = sorted({ensure_hhmm(item) for item in value})
        return normalized


class MedicationOut(BaseModel):
    id: str
    user_id: str
    name: str
    schedule_times: list[str]
    course_days: int | None
    started_at: date
    note: str | None = None
    active: bool
    created_at: str


class UserSettingsUpdate(BaseModel):
    elderly_mode: bool | None = None
    relative_contact: str | None = None
    repeat_reminder_minutes: int | None = Field(default=None, ge=1, le=120)


class UserSettingsResponse(BaseModel):
    user_id: str
    elderly_mode: bool
    relative_contact: str | None = None
    repeat_reminder_minutes: int


class IntakeConfirmRequest(BaseModel):
    user_id: str
    medication_name: str | None = None


class SnoozeRequest(BaseModel):
    user_id: str
    medication_name: str | None = None
    minutes: int = Field(default=10, ge=1, le=120)


class ReminderScanResponse(BaseModel):
    created_notifications: int


class NotificationOut(BaseModel):
    id: str
    user_id: str
    medication_name: str
    type: str
    message: str
    created_at: str
    delivered: bool


class NotificationListResponse(BaseModel):
    items: list[NotificationOut]


class CourseStatusResponse(BaseModel):
    medication_name: str
    course_days: int | None
    current_day: int | None
    completed: bool
    message: str


class DrugInfoResponse(BaseModel):
    name: str
    answer: str
    contraindications: list[str]
    disclaimer: str


class PharmacyOption(BaseModel):
    pharmacy_name: str
    address: str
    price: float
    in_stock: bool
    distance_km: float | None = None


class PharmacySearchResponse(BaseModel):
    drug_name: str
    results: list[PharmacyOption]
    disclaimer: str


class VoiceRequest(BaseModel):
    user_id: str
    utterance: str | None = None
    intent: str | None = None
    slots: dict[str, Any] = Field(default_factory=dict)


class VoiceResponse(BaseModel):
    text: str
    intent: str | None = None
    disclaimer: str | None = None
    data: dict[str, Any] = Field(default_factory=dict)
    suggestions: list[str] = Field(default_factory=list)
    auto_listening: bool = False
    finished: bool = False
    audio_cue: str | None = None
    emotion: str | None = None
    screen_title: str | None = None
    screen_lines: list[str] = Field(default_factory=list)
    speak_disclaimer: bool = False


class SmartAppUUID(BaseModel):
    model_config = ConfigDict(extra="ignore")

    userChannel: str | None = None
    sub: str | None = None
    userId: str | int | None = None


class SmartAppScreenCapability(BaseModel):
    model_config = ConfigDict(extra="ignore")

    available: bool | None = None


class SmartAppSpeakCapability(BaseModel):
    model_config = ConfigDict(extra="ignore")

    available: bool | None = None


class SmartAppCapabilities(BaseModel):
    model_config = ConfigDict(extra="ignore")

    screen: SmartAppScreenCapability | None = None
    speak: SmartAppSpeakCapability | None = None


class SmartAppDevice(BaseModel):
    model_config = ConfigDict(extra="ignore")

    surface: str | None = None
    capabilities: SmartAppCapabilities | None = None


class SmartAppScreenFeature(BaseModel):
    model_config = ConfigDict(extra="ignore")

    enabled: bool | None = None


class SmartAppFeatures(BaseModel):
    model_config = ConfigDict(extra="ignore")

    screen: SmartAppScreenFeature | None = None


class SmartAppMeta(BaseModel):
    model_config = ConfigDict(extra="ignore")

    features: SmartAppFeatures | None = None


class SmartAppMessage(BaseModel):
    model_config = ConfigDict(extra="ignore")

    original_text: str | None = None


class SmartAppServerAction(BaseModel):
    model_config = ConfigDict(extra="ignore")

    action_id: str | None = None
    parameters: dict[str, Any] = Field(default_factory=dict)


class SmartAppPayload(BaseModel):
    model_config = ConfigDict(extra="ignore")

    meta: SmartAppMeta | None = None
    device: SmartAppDevice | None = None
    new_session: bool = False
    message: SmartAppMessage | None = None
    server_action: SmartAppServerAction | None = None
    intent: str | None = None


class SmartAppRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    sessionId: str
    messageId: int
    messageName: str
    uuid: SmartAppUUID
    payload: SmartAppPayload
