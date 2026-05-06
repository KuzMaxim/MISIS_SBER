from __future__ import annotations

from datetime import datetime, timedelta

from fastapi.testclient import TestClient

from app.main import create_app


def build_client(tmp_path):
    app = create_app(state_file=tmp_path / "runtime_state.json", start_scheduler=False)
    return TestClient(app)


def smartapp_request(
    *,
    message_name: str,
    text: str | None = None,
    message_id: int = 1,
    user_id: str = "smart-user",
    has_screen: bool = True,
    new_session: bool = False,
):
    payload = {
        "meta": {"features": {"screen": {"enabled": has_screen}}},
        "device": {
            "surface": "SBERBOX" if has_screen else "SBERBOOM",
            "capabilities": {
                "screen": {"available": has_screen},
                "speak": {"available": True},
            },
        },
        "new_session": new_session,
        "intent": None,
    }
    if text is not None:
        payload["message"] = {"original_text": text}

    return {
        "sessionId": f"session-{user_id}",
        "messageId": message_id,
        "messageName": message_name,
        "uuid": {
            "userChannel": "B2C",
            "sub": user_id,
            "userId": user_id,
        },
        "payload": payload,
    }


def test_sber_run_app_returns_screen_and_audio(tmp_path):
    client = build_client(tmp_path)

    response = client.post(
        "/api/v1/sber/webhook",
        json=smartapp_request(message_name="RUN_APP", has_screen=True),
    )
    body = response.json()

    assert response.status_code == 200
    assert body["messageName"] == "ANSWER_TO_USER"
    assert body["payload"]["pronounceTextType"] == "application/ssml"
    assert "<audio" in body["payload"]["pronounceText"]
    assert body["payload"]["auto_listening"] is True
    assert body["payload"]["finished"] is False
    assert body["payload"]["items"][0]["bubble"]["text"]
    assert body["payload"]["items"][1]["card"]["type"] == "list_card"
    assert body["payload"]["suggestions"]["buttons"]


def test_sber_multistep_add_medication_e2e(tmp_path):
    client = build_client(tmp_path)

    step1 = client.post(
        "/api/v1/sber/webhook",
        json=smartapp_request(message_name="MESSAGE_TO_SKILL", text="Добавь лекарство", message_id=1),
    ).json()
    assert step1["payload"]["auto_listening"] is True
    assert "Как называется препарат" in step1["payload"]["items"][0]["bubble"]["text"]

    step2 = client.post(
        "/api/v1/sber/webhook",
        json=smartapp_request(message_name="MESSAGE_TO_SKILL", text="Аспирин", message_id=2),
    ).json()
    assert "Когда принимать" in step2["payload"]["items"][0]["bubble"]["text"]

    step3 = client.post(
        "/api/v1/sber/webhook",
        json=smartapp_request(message_name="MESSAGE_TO_SKILL", text="Каждый день в 9 утра", message_id=3),
    ).json()
    assert "Сколько дней курс" in step3["payload"]["items"][0]["bubble"]["text"]

    step4 = client.post(
        "/api/v1/sber/webhook",
        json=smartapp_request(message_name="MESSAGE_TO_SKILL", text="7 дней", message_id=4),
    ).json()
    assert "расписание" in step4["payload"]["items"][0]["bubble"]["text"].lower()
    assert "добавлен" in step4["payload"]["items"][0]["bubble"]["text"].lower()
    assert step4["payload"]["items"][1]["card"]["cells"][1]["content"]["text"] == "Время: 09:00"

    meds = client.get("/api/v1/medications/smart-user").json()
    assert len(meds) == 1
    assert meds[0]["name"] == "Аспирин"


def test_sber_screen_search_and_safe_refusal_e2e(tmp_path):
    client = build_client(tmp_path)

    search = client.post(
        "/api/v1/sber/webhook",
        json=smartapp_request(
            message_name="MESSAGE_TO_SKILL",
            text="Где купить ибупрофен подешевле",
            message_id=10,
        ),
    ).json()
    search_cells = search["payload"]["items"][1]["card"]["cells"]
    assert search["payload"]["items"][1]["card"]["type"] == "list_card"
    assert any("Аптеки: ибупрофен" in cell["content"]["text"] for cell in search_cells)
    assert any("₽" in cell["content"]["text"] or "руб" in cell["content"]["text"].lower() for cell in search_cells)

    refusal = client.post(
        "/api/v1/sber/webhook",
        json=smartapp_request(
            message_name="MESSAGE_TO_SKILL",
            text="Что мне принимать от давления?",
            message_id=11,
        ),
    ).json()
    refusal_cells = refusal["payload"]["items"][1]["card"]["cells"]
    assert "не могу" in refusal["payload"]["items"][0]["bubble"]["text"].lower()
    assert any("не заменяет консультацию врача" in cell["content"]["text"].lower() for cell in refusal_cells)


def test_sber_no_screen_and_reminder_confirm_flow_e2e(tmp_path):
    client = build_client(tmp_path)
    schedule_time = (datetime.now().replace(second=0, microsecond=0) - timedelta(minutes=1)).strftime("%H:%M")

    add = client.post(
        "/api/v1/sber/webhook",
        json=smartapp_request(
            message_name="MESSAGE_TO_SKILL",
            text=f"Напомни принимать ибупрофен каждый день в {schedule_time} без курса",
            message_id=20,
            has_screen=False,
        ),
    ).json()
    assert len(add["payload"]["items"]) == 1
    assert add["payload"]["pronounceTextType"] == "application/ssml"

    scan_response = client.post("/api/v1/dev/scan-reminders")
    assert scan_response.status_code == 200
    assert scan_response.json()["created_notifications"] >= 1

    confirm = client.post(
        "/api/v1/sber/webhook",
        json=smartapp_request(
            message_name="MESSAGE_TO_SKILL",
            text="Принял ибупрофен",
            message_id=21,
            has_screen=False,
        ),
    ).json()
    assert "подтверждён" in confirm["payload"]["items"][0]["bubble"]["text"].lower()
    assert confirm["payload"]["finished"] is False


def test_sber_exit_flow_e2e(tmp_path):
    client = build_client(tmp_path)

    response = client.post(
        "/api/v1/sber/webhook",
        json=smartapp_request(
            message_name="MESSAGE_TO_SKILL",
            text="Выход",
            message_id=30,
        ),
    )
    body = response.json()

    assert response.status_code == 200
    assert body["payload"]["finished"] is True
    assert body["payload"]["auto_listening"] is False
