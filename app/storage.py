from __future__ import annotations

import copy
import json
from pathlib import Path
from threading import RLock
from typing import Any, Callable, TypeVar


T = TypeVar("T")


class JsonStorage:
    def __init__(self, state_file: Path):
        self.state_file = state_file
        self._lock = RLock()
        self._ensure_state_file()

    @staticmethod
    def default_state() -> dict[str, Any]:
        return {
            "users": {},
            "medications": {},
            "intake_history": {},
            "notifications": {},
            "dialog_sessions": {},
        }

    def _ensure_state_file(self) -> None:
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        if not self.state_file.exists():
            self.state_file.write_text(
                json.dumps(self.default_state(), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

    def _read_unlocked(self) -> dict[str, Any]:
        raw = self.state_file.read_text(encoding="utf-8")
        if not raw.strip():
            return self.default_state()
        return json.loads(raw)

    def _write_unlocked(self, state: dict[str, Any]) -> None:
        self.state_file.write_text(
            json.dumps(state, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def read(self) -> dict[str, Any]:
        with self._lock:
            return copy.deepcopy(self._read_unlocked())

    def transaction(self, callback: Callable[[dict[str, Any]], T]) -> T:
        with self._lock:
            state = self._read_unlocked()
            result = callback(state)
            self._write_unlocked(state)
            return result


def load_json_file(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))

