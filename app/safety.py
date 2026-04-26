from __future__ import annotations

import re

SAFE_DISCLAIMER = "Информация носит справочный характер и не заменяет консультацию врача."

PERSONAL_MEDICAL_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in [
        r"что мне принимать",
        r"что лучше принимать",
        r"какое лекарство мне",
        r"назнач(ь|ите)",
        r"можно ли мне принимать",
        r"поставь диагноз",
        r"замени врача",
    ]
]


def requires_medical_refusal(text: str | None) -> bool:
    if not text:
        return False
    return any(pattern.search(text) for pattern in PERSONAL_MEDICAL_PATTERNS)


def medical_refusal_text() -> str:
    return (
        "Я не могу ставить диагнозы, назначать лечение или давать индивидуальные "
        "рекомендации. Могу сообщить только справочную информацию по инструкции. "
        "Обратитесь к врачу."
    )

