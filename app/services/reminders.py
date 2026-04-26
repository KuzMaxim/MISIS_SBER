from __future__ import annotations

from datetime import datetime, timedelta
from uuid import uuid4

from app.config import MAX_REMINDER_ATTEMPTS
from app.storage import JsonStorage
from app.utils import local_now, parse_iso_date, parse_iso_datetime


class ReminderService:
    def __init__(self, storage: JsonStorage):
        self.storage = storage

    def _create_notification(
        self,
        state: dict,
        *,
        user_id: str,
        medication: dict,
        intake_id: str,
        notification_type: str,
        message: str,
        now: datetime,
    ) -> dict:
        notification_id = str(uuid4())
        notification = {
            "id": notification_id,
            "user_id": user_id,
            "medication_id": medication["id"],
            "medication_name": medication["name"],
            "intake_id": intake_id,
            "type": notification_type,
            "message": message,
            "created_at": now.isoformat(),
            "delivered": False,
        }
        state["notifications"][notification_id] = notification
        return notification

    @staticmethod
    def _compose_message(medication_name: str, elderly_mode: bool, is_repeat: bool = False) -> str:
        if elderly_mode:
            prefix = "Повторяю." if is_repeat else "Напоминание."
            return (
                f"{prefix} Пора принять {medication_name}. "
                "Скажите: принял или отложить."
            )
        if is_repeat:
            return (
                f"Повторное напоминание: пора принять {medication_name}. "
                "Вы уже приняли лекарство?"
            )
        return f"Напоминание: пора принять {medication_name}. Вы приняли лекарство?"

    def scan(self, now: datetime | None = None) -> list[dict]:
        scan_time = (now or local_now()).replace(second=0, microsecond=0)

        def mutate(state: dict) -> list[dict]:
            created_notifications: list[dict] = []

            for medication in state["medications"].values():
                if not medication["active"]:
                    continue

                course_days = medication.get("course_days")
                if course_days:
                    started_at = parse_iso_date(medication["started_at"])
                    if scan_time.date() > started_at + timedelta(days=course_days - 1):
                        medication["active"] = False
                        continue

                for time_value in medication["schedule_times"]:
                    scheduled_for = datetime.combine(
                        scan_time.date(), datetime.strptime(time_value, "%H:%M").time()
                    )
                    if scheduled_for > scan_time:
                        continue

                    already_exists = any(
                        record["medication_id"] == medication["id"]
                        and record["scheduled_for"] == scheduled_for.isoformat()
                        for record in state["intake_history"].values()
                    )
                    if already_exists:
                        continue

                    intake_id = str(uuid4())
                    intake = {
                        "id": intake_id,
                        "user_id": medication["user_id"],
                        "medication_id": medication["id"],
                        "medication_name": medication["name"],
                        "normalized_name": medication["normalized_name"],
                        "scheduled_for": scheduled_for.isoformat(),
                        "status": "pending",
                        "confirmed_at": None,
                        "reminder_attempts": 1,
                        "last_reminded_at": scan_time.isoformat(),
                        "snoozed_until": None,
                    }
                    state["intake_history"][intake_id] = intake

                    user = state["users"].get(medication["user_id"], {})
                    message = self._compose_message(
                        medication["name"],
                        elderly_mode=bool(user.get("elderly_mode")),
                    )
                    created_notifications.append(
                        self._create_notification(
                            state,
                            user_id=medication["user_id"],
                            medication=medication,
                            intake_id=intake_id,
                            notification_type="initial",
                            message=message,
                            now=scan_time,
                        )
                    )

            for record in state["intake_history"].values():
                if record["status"] == "taken" or record["status"] == "missed":
                    continue

                medication = state["medications"].get(record["medication_id"])
                if not medication:
                    continue
                user = state["users"].get(record["user_id"], {})

                if record["status"] == "snoozed":
                    snoozed_until = parse_iso_datetime(record["snoozed_until"])
                    if snoozed_until and snoozed_until <= scan_time:
                        record["status"] = "pending"
                        record["reminder_attempts"] += 1
                        record["last_reminded_at"] = scan_time.isoformat()
                        created_notifications.append(
                            self._create_notification(
                                state,
                                user_id=record["user_id"],
                                medication=medication,
                                intake_id=record["id"],
                                notification_type="repeat",
                                message=self._compose_message(
                                    medication["name"],
                                    elderly_mode=bool(user.get("elderly_mode")),
                                    is_repeat=True,
                                ),
                                now=scan_time,
                            )
                        )
                    continue

                last_reminded_at = parse_iso_datetime(record["last_reminded_at"])
                repeat_minutes = int(user.get("repeat_reminder_minutes", 10))
                if not last_reminded_at or last_reminded_at + timedelta(minutes=repeat_minutes) > scan_time:
                    continue

                if record["reminder_attempts"] >= MAX_REMINDER_ATTEMPTS:
                    record["status"] = "missed"
                    if user.get("relative_contact"):
                        created_notifications.append(
                            self._create_notification(
                                state,
                                user_id=record["user_id"],
                                medication=medication,
                                intake_id=record["id"],
                                notification_type="relative_alert",
                                message=(
                                    f"Пользователь не подтвердил приём {medication['name']}. "
                                    f"Нужно уведомить контакт: {user['relative_contact']}."
                                ),
                                now=scan_time,
                            )
                        )
                    continue

                record["reminder_attempts"] += 1
                record["last_reminded_at"] = scan_time.isoformat()
                created_notifications.append(
                    self._create_notification(
                        state,
                        user_id=record["user_id"],
                        medication=medication,
                        intake_id=record["id"],
                        notification_type="repeat",
                        message=self._compose_message(
                            medication["name"],
                            elderly_mode=bool(user.get("elderly_mode")),
                            is_repeat=True,
                        ),
                        now=scan_time,
                    )
                )

            return created_notifications

        return self.storage.transaction(mutate)

    def get_notifications(self, user_id: str, consume: bool = False) -> list[dict]:
        def mutate(state: dict) -> list[dict]:
            notifications = [
                notification
                for notification in state["notifications"].values()
                if notification["user_id"] == user_id and not notification["delivered"]
            ]
            notifications.sort(key=lambda item: item["created_at"], reverse=True)
            if consume:
                for notification in notifications:
                    notification["delivered"] = True
            return [dict(item) for item in notifications]

        if consume:
            return self.storage.transaction(mutate)

        state = self.storage.read()
        notifications = [
            notification
            for notification in state["notifications"].values()
            if notification["user_id"] == user_id and not notification["delivered"]
        ]
        notifications.sort(key=lambda item: item["created_at"], reverse=True)
        return notifications

