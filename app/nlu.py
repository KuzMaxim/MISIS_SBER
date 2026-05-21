from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from app.utils import normalize_text, parse_time_fragment

COURSE_NUMBER_WORDS = {
    "один": 1,
    "одна": 1,
    "два": 2,
    "две": 2,
    "три": 3,
    "четыре": 4,
    "пять": 5,
    "шесть": 6,
    "семь": 7,
    "восемь": 8,
    "девять": 9,
    "десять": 10,
    "одиннадцать": 11,
    "двенадцать": 12,
    "тринадцать": 13,
    "четырнадцать": 14,
    "пятнадцать": 15,
    "шестнадцать": 16,
    "семнадцать": 17,
    "восемнадцать": 18,
    "девятнадцать": 19,
    "двадцать": 20,
    "двадцать один": 21,
    "двадцать два": 22,
    "двадцать три": 23,
    "двадцать четыре": 24,
    "двадцать пять": 25,
    "двадцать шесть": 26,
    "двадцать семь": 27,
    "двадцать восемь": 28,
    "двадцать девять": 29,
    "тридцать": 30,
}

COURSE_NUMBER_PATTERN = re.compile(
    r"\b("
    + "|".join(sorted(map(re.escape, COURSE_NUMBER_WORDS), key=len, reverse=True))
    + r")\b"
)


@dataclass
class ParsedIntent:
    intent: str
    slots: dict[str, Any] = field(default_factory=dict)


def extract_course_details(text: str) -> dict[str, Any]:
    lowered = normalize_text(text)
    if "без курса" in lowered:
        return {"course_days": None, "course_provided": True}

    match = re.search(r"\b(?P<days>\d{1,3})\s*(день|дня|дней)\b", lowered)
    if match:
        return {"course_days": int(match.group("days")), "course_provided": True}

    word_match = COURSE_NUMBER_PATTERN.search(lowered)
    if word_match and re.search(r"\b(день|дня|дней|сутки|суток)\b", lowered):
        return {
            "course_days": COURSE_NUMBER_WORDS[word_match.group(1)],
            "course_provided": True,
        }

    return {"course_days": None, "course_provided": False}


def parse_utterance(text: str) -> ParsedIntent:
    lowered = normalize_text(text)

    if lowered in {"помощь", "справка", "что ты умеешь", "что умеешь"}:
        return ParsedIntent("Помощь", {})

    if lowered in {"выход", "стоп", "закрыть", "закрой навык", "завершить"}:
        return ParsedIntent("Завершить", {})

    if lowered in {
        "мои лекарства",
        "покажи лекарства",
        "показать лекарства",
        "что я принимаю",
        "мое расписание",
    }:
        return ParsedIntent("ПоказатьЛекарства", {})

    if any(
        token in lowered
        for token in [
            "добавь лекарство",
            "добавь лекарства",
            "добавить лекарство",
            "добавить лекарства",
        ]
    ):
        return ParsedIntent("ДобавитьЛекарство", {})

    reminder_match = re.search(
        r"напомни(?:\s+мне)?(?:\s+(?:принимать|пить))?\s+(?P<name>.+?)\s+каждый день(?:\s+в)?\s+(?P<time>.+)$",
        lowered,
    )
    if reminder_match:
        schedule_time = parse_time_fragment(reminder_match.group("time"))
        slots = {
            "name": reminder_match.group("name").strip(" .,!?:;"),
            "schedule_times": [schedule_time] if schedule_time else [],
        }
        slots.update(extract_course_details(lowered))
        return ParsedIntent("ДобавитьЛекарство", slots)

    add_match = re.search(r"^(?:добавь|добавить)\s+(?P<name>.+)$", lowered)
    if add_match:
        name = add_match.group("name").strip(" .,!?:;")
        if name not in {"лекарство", "лекарства"}:
            return ParsedIntent(
                "ДобавитьЛекарство",
                {
                    "name": name,
                    "course_provided": False,
                },
            )

    if lowered in {"принял", "приняла", "я принял", "я приняла"}:
        return ParsedIntent("ПодтвердитьПрием", {})

    confirm_match = re.search(r"(?:принял|приняла)\s+(?P<name>.+)$", lowered)
    if confirm_match:
        return ParsedIntent(
            "ПодтвердитьПрием",
            {"name": confirm_match.group("name").strip(" .,!?:;")},
        )

    snooze_match = re.search(
        r"(?:отложи|напомни позже)(?:\s+на\s+(?P<minutes>\d{1,3})\s+минут)?(?:\s+(?P<name>.+))?$",
        lowered,
    )
    if snooze_match:
        return ParsedIntent(
            "ОтложитьНапоминание",
            {
                "minutes": int(snooze_match.group("minutes") or 10),
                "name": (snooze_match.group("name") or "").strip(" .,!?:;") or None,
            },
        )

    if "день курса" in lowered or "дней осталось" in lowered:
        name = None
        match = re.search(r"(?:курса|осталось)\s+(?P<name>.+)$", lowered)
        if match:
            name = match.group("name").strip(" .,!?:;")
        return ParsedIntent("СпроситьОКурсе", {"name": name})

    pharmacy_match = re.search(r"где купить\s+(?P<name>.+?)(?:\s+подешевле)?$", lowered)
    if pharmacy_match:
        return ParsedIntent(
            "ПоискАптеки",
            {"name": pharmacy_match.group("name").strip(" .,!?:;")},
        )

    info_usage_match = re.search(r"для чего(?:\s+используется)?\s+(?P<name>.+)$", lowered)
    if info_usage_match:
        return ParsedIntent(
            "СправкаОПрепарате",
            {"name": info_usage_match.group("name").strip(" .,!?:;")},
        )

    info_contra_match = re.search(r"какие(?:\s+есть)?\s+противопоказания(?:\s+у)?\s+(?P<name>.+)$", lowered)
    if info_contra_match:
        return ParsedIntent(
            "СправкаОПрепарате",
            {"name": info_contra_match.group("name").strip(" .,!?:;")},
        )

    return ParsedIntent("Неизвестно", {})
