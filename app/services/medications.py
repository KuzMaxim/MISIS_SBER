from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from app.config import DEFAULT_REPEAT_MINUTES
from app.schemas import MedicationCreate, UserSettingsUpdate
from app.storage import JsonStorage
from app.utils import (
    add_minutes,
    format_schedule_times,
    local_now,
    normalize_medication_name,
    parse_iso_date,
    parse_iso_datetime,
)


class MedicationService:
    def __init__(self, storage: JsonStorage):
        self.storage = storage

    @staticmethod
    def _default_user(user_id: str) -> dict:
        return {
            "id": user_id,
            "elderly_mode": False,
            "repeat_reminder_minutes": DEFAULT_REPEAT_MINUTES,
            "relative_contact": None,
        }

    def ensure_user(self, user_id: str) -> dict:
        def mutate(state: dict) -> dict:
            user = state["users"].setdefault(user_id, self._default_user(user_id))
            return dict(user)

        return self.storage.transaction(mutate)

    def get_user_settings(self, user_id: str) -> dict:
        state = self.storage.read()
        user = state["users"].get(user_id)
        if not user:
            user = self.ensure_user(user_id)
        return user

    def update_user_settings(self, user_id: str, payload: UserSettingsUpdate) -> dict:
        def mutate(state: dict) -> dict:
            user = state["users"].setdefault(user_id, self._default_user(user_id))
            updates = payload.model_dump(exclude_none=True)
            user.update(updates)
            return dict(user)

        return self.storage.transaction(mutate)

    def list_medications(self, user_id: str) -> list[dict]:
        state = self.storage.read()
        medications = [
            medication
            for medication in state["medications"].values()
            if medication["user_id"] == user_id
        ]
        medications.sort(key=lambda item: item["created_at"])
        return medications

    def add_or_update_medication(self, payload: MedicationCreate) -> tuple[dict, bool]:
        self.ensure_user(payload.user_id)
        now = local_now().isoformat()
        normalized_name = normalize_medication_name(payload.name)

        def mutate(state: dict) -> tuple[dict, bool]:
            for medication in state["medications"].values():
                if (
                    medication["user_id"] == payload.user_id
                    and medication["normalized_name"] == normalized_name
                ):
                    merged_times = sorted(
                        {*(medication["schedule_times"]), *payload.schedule_times}
                    )
                    medication["schedule_times"] = merged_times
                    medication["course_days"] = payload.course_days
                    medication["started_at"] = payload.started_at.isoformat()
                    medication["note"] = payload.note
                    medication["active"] = True
                    return dict(medication), False

            medication_id = str(uuid4())
            medication = {
                "id": medication_id,
                "user_id": payload.user_id,
                "name": payload.name,
                "normalized_name": normalized_name,
                "schedule_times": payload.schedule_times,
                "course_days": payload.course_days,
                "started_at": payload.started_at.isoformat(),
                "note": payload.note,
                "active": True,
                "created_at": now,
            }
            state["medications"][medication_id] = medication
            return dict(medication), True

        return self.storage.transaction(mutate)

    def find_medication(self, state: dict, user_id: str, medication_name: str | None) -> dict | None:
        user_medications = [
            medication
            for medication in state["medications"].values()
            if medication["user_id"] == user_id and medication["active"]
        ]
        if medication_name:
            normalized = normalize_medication_name(medication_name)
            for medication in user_medications:
                if medication["normalized_name"] == normalized:
                    return medication
            return None

        if len(user_medications) == 1:
            return user_medications[0]
        return None

    def get_course_status(self, user_id: str, medication_name: str | None) -> dict:
        state = self.storage.read()
        medication = self.find_medication(state, user_id, medication_name)
        if not medication:
            return {
                "medication_name": medication_name or "",
                "course_days": None,
                "current_day": None,
                "completed": False,
                "message": "Не удалось определить лекарство для проверки курса.",
            }

        course_days = medication.get("course_days")
        if not course_days:
            return {
                "medication_name": medication["name"],
                "course_days": None,
                "current_day": None,
                "completed": False,
                "message": "Для этого лекарства курс не задан.",
            }

        started_at = parse_iso_date(medication["started_at"])
        today = local_now().date()
        current_day = (today - started_at).days + 1
        completed = current_day > course_days
        if completed:
            message = f"Курс препарата {medication['name']} завершён."
            current_day = course_days
        else:
            message = f"Сегодня {current_day}-й день курса препарата {medication['name']}."

        return {
            "medication_name": medication["name"],
            "course_days": course_days,
            "current_day": current_day,
            "completed": completed,
            "message": message,
        }

    def confirm_intake(self, user_id: str, medication_name: str | None = None) -> dict | None:
        now = local_now()

        def mutate(state: dict) -> dict | None:
            pending_records = [
                record
                for record in state["intake_history"].values()
                if record["user_id"] == user_id and record["status"] in {"pending", "snoozed"}
            ]
            pending_records.sort(key=lambda item: item["scheduled_for"], reverse=True)
            normalized_target = (
                normalize_medication_name(medication_name) if medication_name else None
            )

            for record in pending_records:
                if normalized_target and record["normalized_name"] != normalized_target:
                    continue
                record["status"] = "taken"
                record["confirmed_at"] = now.isoformat()
                record["snoozed_until"] = None
                return dict(record)
            return None

        return self.storage.transaction(mutate)

    def snooze_intake(self, user_id: str, minutes: int, medication_name: str | None = None) -> dict | None:
        now = local_now()

        def mutate(state: dict) -> dict | None:
            pending_records = [
                record
                for record in state["intake_history"].values()
                if record["user_id"] == user_id and record["status"] == "pending"
            ]
            pending_records.sort(key=lambda item: item["scheduled_for"], reverse=True)
            normalized_target = (
                normalize_medication_name(medication_name) if medication_name else None
            )

            for record in pending_records:
                if normalized_target and record["normalized_name"] != normalized_target:
                    continue
                record["status"] = "snoozed"
                record["snoozed_until"] = add_minutes(now, minutes).isoformat()
                return dict(record)
            return None

        return self.storage.transaction(mutate)

    def build_add_message(self, medication: dict) -> str:
        schedule = format_schedule_times(medication["schedule_times"])
        course_days = medication.get("course_days")
        if course_days:
            return (
                f"Добавила {medication['name']} в расписание. Напоминание каждый день в "
                f"{schedule}. Курс: {course_days} дней."
            )
        return (
            f"Добавила {medication['name']} в расписание. Напоминание каждый день в {schedule}."
        )

