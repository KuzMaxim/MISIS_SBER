from __future__ import annotations

from datetime import datetime, timedelta

from fastapi.testclient import TestClient

from app.main import create_app


def build_client(tmp_path):
    app = create_app(state_file=tmp_path / "runtime_state.json", start_scheduler=False)
    return TestClient(app)


def test_multistep_add_medication_dialog(tmp_path):
    client = build_client(tmp_path)

    response = client.post(
        "/api/v1/skill/handle",
        json={"user_id": "user-1", "utterance": "Добавь лекарство"},
    )
    assert response.status_code == 200
    assert "Как называется препарат" in response.json()["text"]

    response = client.post(
        "/api/v1/skill/handle",
        json={"user_id": "user-1", "utterance": "Аспирин"},
    )
    assert "Когда принимать" in response.json()["text"]

    response = client.post(
        "/api/v1/skill/handle",
        json={"user_id": "user-1", "utterance": "Каждый день в 9 утра"},
    )
    assert "Сколько дней курс" in response.json()["text"]

    response = client.post(
        "/api/v1/skill/handle",
        json={"user_id": "user-1", "utterance": "7 дней"},
    )
    assert "добавила" in response.json()["text"].lower()
    assert "в расписание" in response.json()["text"].lower()

    medications = client.get("/api/v1/medications/user-1").json()
    assert len(medications) == 1
    assert medications[0]["name"] == "Аспирин"
    assert medications[0]["schedule_times"] == ["09:00"]
    assert medications[0]["course_days"] == 7


def test_reminder_scan_and_confirm_flow(tmp_path):
    client = build_client(tmp_path)
    now = datetime.now().replace(second=0, microsecond=0) - timedelta(minutes=1)

    add_response = client.post(
        "/api/v1/medications",
        json={
            "user_id": "user-2",
            "name": "Ибупрофен",
            "schedule_times": [now.strftime("%H:%M")],
            "course_days": 5,
            "started_at": now.date().isoformat(),
        },
    )
    assert add_response.status_code == 200

    scan_response = client.post("/api/v1/dev/scan-reminders")
    assert scan_response.status_code == 200
    assert scan_response.json()["created_notifications"] >= 1

    notifications = client.get("/api/v1/notifications/user-2?consume=true").json()["items"]
    assert notifications
    assert notifications[0]["type"] == "initial"

    confirm_response = client.post(
        "/api/v1/intake/confirm",
        json={"user_id": "user-2", "medication_name": "Ибупрофен"},
    )
    assert confirm_response.status_code == 200
    assert "подтверждён" in confirm_response.json()["message"].lower()


def test_drug_info_returns_disclaimer(tmp_path):
    client = build_client(tmp_path)

    response = client.get("/api/v1/drug-info?name=парацетамол")
    body = response.json()

    assert response.status_code == 200
    assert body["answer"].startswith("По инструкции препарат используется")
    assert "не заменяет консультацию врача" in body["disclaimer"].lower()


def test_medical_advice_request_is_blocked(tmp_path):
    client = build_client(tmp_path)

    response = client.post(
        "/api/v1/skill/handle",
        json={"user_id": "user-3", "utterance": "Что мне принимать от давления?"},
    )
    body = response.json()

    assert response.status_code == 200
    assert body["intent"] == "БезопасныйОтказ"
    assert "не могу" in body["text"].lower()
