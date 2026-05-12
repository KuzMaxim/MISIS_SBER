from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Query, Response

from app.config import (
    DEFAULT_REMINDER_INTERVAL_SECONDS,
    DRUG_REFERENCE_FILE,
    PHARMACY_FILE,
    STATE_FILE,
)
from app.schemas import (
    CourseStatusResponse,
    DrugInfoResponse,
    IntakeConfirmRequest,
    MedicationCreate,
    MedicationOut,
    NotificationListResponse,
    OperationResponse,
    PharmacySearchResponse,
    ReminderScanResponse,
    SnoozeRequest,
    SmartAppRequest,
    UserSettingsResponse,
    UserSettingsUpdate,
    VoiceRequest,
    VoiceResponse,
)
from app.services.dialog import DialogService
from app.services.drug_info import DrugInfoService
from app.services.medications import MedicationService
from app.services.pharmacy import PharmacyService
from app.services.reminders import ReminderService
from app.services.smartapp import SmartAppService
from app.storage import JsonStorage


async def reminder_loop(app: FastAPI, interval_seconds: int, stop_event: asyncio.Event) -> None:
    while not stop_event.is_set():
        app.state.reminder_service.scan()
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=interval_seconds)
        except asyncio.TimeoutError:
            continue


def create_app(
    *,
    state_file: Path | None = None,
    start_scheduler: bool = True,
    reminder_interval_seconds: int = DEFAULT_REMINDER_INTERVAL_SECONDS,
) -> FastAPI:
    storage = JsonStorage(state_file or STATE_FILE)
    medication_service = MedicationService(storage)
    reminder_service = ReminderService(storage)
    drug_info_service = DrugInfoService(DRUG_REFERENCE_FILE)
    pharmacy_service = PharmacyService(PHARMACY_FILE)
    dialog_service = DialogService(
        storage,
        medication_service,
        drug_info_service,
        pharmacy_service,
    )
    smartapp_service = SmartAppService(dialog_service, medication_service)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.storage = storage
        app.state.medication_service = medication_service
        app.state.reminder_service = reminder_service
        app.state.drug_info_service = drug_info_service
        app.state.pharmacy_service = pharmacy_service
        app.state.dialog_service = dialog_service
        app.state.smartapp_service = smartapp_service

        stop_event = asyncio.Event()
        task = None
        if start_scheduler:
            task = asyncio.create_task(
                reminder_loop(app, reminder_interval_seconds, stop_event)
            )

        yield

        stop_event.set()
        if task is not None:
            await task

    app = FastAPI(
        title="Умный помощник здоровья",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.state.storage = storage
    app.state.medication_service = medication_service
    app.state.reminder_service = reminder_service
    app.state.drug_info_service = drug_info_service
    app.state.pharmacy_service = pharmacy_service
    app.state.dialog_service = dialog_service
    app.state.smartapp_service = smartapp_service

    @app.get("/health")
    def healthcheck() -> dict:
        return {"status": "ok"}

    @app.post("/api/v1/skill/handle", response_model=VoiceResponse)
    def handle_skill(request: VoiceRequest) -> VoiceResponse:
        return app.state.dialog_service.handle(request)

    def handle_sber_request(request: SmartAppRequest):
        response_body = app.state.smartapp_service.handle(request)
        if response_body is None:
            return Response(status_code=204)
        return response_body

    @app.post("/")
    def handle_sber_root_webhook(request: SmartAppRequest):
        return handle_sber_request(request)

    @app.post("/api/v1/sber/webhook")
    def handle_sber_webhook(request: SmartAppRequest):
        return handle_sber_request(request)

    @app.post("/api/v1/medications", response_model=OperationResponse)
    def add_medication(payload: MedicationCreate) -> OperationResponse:
        medication, _created = app.state.medication_service.add_or_update_medication(payload)
        return OperationResponse(
            message=app.state.medication_service.build_add_message(medication),
            data=medication,
        )

    @app.get("/api/v1/medications/{user_id}", response_model=list[MedicationOut])
    def list_medications(user_id: str) -> list[dict]:
        return app.state.medication_service.list_medications(user_id)

    @app.patch("/api/v1/users/{user_id}/settings", response_model=UserSettingsResponse)
    def update_settings(user_id: str, payload: UserSettingsUpdate) -> dict:
        return app.state.medication_service.update_user_settings(user_id, payload)

    @app.post("/api/v1/intake/confirm", response_model=OperationResponse)
    def confirm_intake(payload: IntakeConfirmRequest) -> OperationResponse:
        record = app.state.medication_service.confirm_intake(
            payload.user_id,
            payload.medication_name,
        )
        if not record:
            return OperationResponse(message="Активное напоминание не найдено.")
        return OperationResponse(
            message=f"Приём препарата {record['medication_name']} подтверждён.",
            data=record,
        )

    @app.post("/api/v1/intake/snooze", response_model=OperationResponse)
    def snooze_intake(payload: SnoozeRequest) -> OperationResponse:
        record = app.state.medication_service.snooze_intake(
            payload.user_id,
            payload.minutes,
            payload.medication_name,
        )
        if not record:
            return OperationResponse(message="Активное напоминание не найдено.")
        return OperationResponse(
            message=(
                f"Напоминание по препарату {record['medication_name']} "
                f"отложено на {payload.minutes} минут."
            ),
            data=record,
        )

    @app.get("/api/v1/course-status", response_model=CourseStatusResponse)
    def get_course_status(
        user_id: str = Query(...),
        medication_name: str | None = Query(default=None),
    ) -> dict:
        return app.state.medication_service.get_course_status(user_id, medication_name)

    @app.get("/api/v1/drug-info", response_model=DrugInfoResponse)
    def get_drug_info(name: str = Query(...)) -> dict:
        return app.state.drug_info_service.get_info(name)

    @app.get("/api/v1/pharmacies/search", response_model=PharmacySearchResponse)
    def search_pharmacies(
        name: str = Query(...),
        user_lat: float | None = Query(default=None),
        user_lon: float | None = Query(default=None),
    ) -> dict:
        return app.state.pharmacy_service.search(
            name,
            user_lat=user_lat,
            user_lon=user_lon,
        )

    @app.get("/api/v1/notifications/{user_id}", response_model=NotificationListResponse)
    def get_notifications(
        user_id: str,
        consume: bool = Query(default=False),
    ) -> NotificationListResponse:
        items = app.state.reminder_service.get_notifications(user_id, consume=consume)
        return NotificationListResponse(items=items)

    @app.post("/api/v1/dev/scan-reminders", response_model=ReminderScanResponse)
    def scan_reminders() -> ReminderScanResponse:
        created_notifications = app.state.reminder_service.scan()
        return ReminderScanResponse(created_notifications=len(created_notifications))

    return app


app = create_app()
