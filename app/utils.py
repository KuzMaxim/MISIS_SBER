from __future__ import annotations

import math
import re
from datetime import date, datetime, timedelta


def single_line_text(value: str) -> str:
    return re.sub(r"\s+", " ", value.replace("\n", " ").replace("\r", " ")).strip()


def normalize_text(value: str) -> str:
    return single_line_text(value).lower()


def normalize_medication_name(value: str) -> str:
    cleaned = normalize_text(value)
    cleaned = re.sub(r"^(таблетки|лекарство|препарат)\s+", "", cleaned)
    return cleaned.strip(" .,!?:;")


def local_now() -> datetime:
    return datetime.now().replace(microsecond=0)


def parse_iso_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value)


def parse_iso_date(value: str | None) -> date | None:
    if not value:
        return None
    return date.fromisoformat(value)


def format_schedule_times(times: list[str]) -> str:
    return ", ".join(sorted(times))


def ensure_hhmm(value: str) -> str:
    hour, minute = value.split(":")
    return f"{int(hour):02d}:{int(minute):02d}"


def parse_time_fragment(text: str) -> str | None:
    lowered = normalize_text(text)
    patterns = [
        re.compile(r"\bв\s*(?P<hour>\d{1,2})(?::(?P<minute>\d{2}))?\s*(?P<period>утра|вечера|дня|ночи)?\b"),
        re.compile(r"\b(?P<hour>\d{1,2}):(?P<minute>\d{2})\b"),
        re.compile(r"^(?P<hour>\d{1,2})\s*(?P<period>утра|вечера|дня|ночи)\b"),
    ]

    for pattern in patterns:
        match = pattern.search(lowered)
        if not match:
            continue

        hour = int(match.group("hour"))
        minute = int(match.group("minute") or 0)
        period = match.groupdict().get("period")

        if period in {"вечера", "дня"} and hour < 12:
            hour += 12
        if period == "ночи" and hour == 12:
            hour = 0
        if period == "утра" and hour == 12:
            hour = 0

        if 0 <= hour <= 23 and 0 <= minute <= 59:
            return f"{hour:02d}:{minute:02d}"
    return None


def add_minutes(moment: datetime, minutes: int) -> datetime:
    return moment + timedelta(minutes=minutes)


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius = 6371.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = (
        math.sin(delta_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return radius * c
