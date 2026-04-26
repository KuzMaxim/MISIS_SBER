from __future__ import annotations

from pathlib import Path

from app.safety import SAFE_DISCLAIMER
from app.storage import load_json_file
from app.utils import normalize_medication_name


class DrugInfoService:
    def __init__(self, reference_file: Path):
        self.reference = load_json_file(reference_file)

    def get_info(self, name: str) -> dict:
        normalized = normalize_medication_name(name)
        entry = self.reference.get(normalized)
        if not entry:
            return {
                "name": name,
                "answer": (
                    "Я не нашёл карточку препарата в локальном справочнике. "
                    "Могу сообщать только справочную информацию по инструкции."
                ),
                "contraindications": [],
                "disclaimer": SAFE_DISCLAIMER,
            }

        return {
            "name": name,
            "answer": f"По инструкции препарат используется для {entry['usage']}.",
            "contraindications": entry["contraindications"],
            "disclaimer": SAFE_DISCLAIMER,
        }

