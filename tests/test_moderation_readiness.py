from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from app.main import create_app


def build_client(tmp_path: Path) -> TestClient:
    app = create_app(state_file=tmp_path / "runtime_state.json", start_scheduler=False)
    return TestClient(app)


def smartapp_request(
    *,
    message_name: str,
    text: str | None = None,
    message_id: int = 1,
    user_id: str = "moderation-user",
    has_screen: bool = True,
    new_session: bool = False,
    server_action_text: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
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
    if server_action_text is not None:
        payload["server_action"] = {
            "action_id": "moderation_text_action",
            "parameters": {"text": server_action_text},
        }

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


def assert_no_nulls_or_newlines(value: Any) -> None:
    if isinstance(value, dict):
        for item in value.values():
            assert_no_nulls_or_newlines(item)
        return
    if isinstance(value, list):
        for item in value:
            assert_no_nulls_or_newlines(item)
        return
    assert value is not None
    if isinstance(value, str):
        assert "\n" not in value
        assert "\r" not in value


def test_smartapp_responses_follow_moderation_contract(tmp_path):
    client = build_client(tmp_path)
    requests = [
        smartapp_request(message_name="RUN_APP", new_session=True, message_id=1),
        smartapp_request(message_name="MESSAGE_TO_SKILL", text="Помощь", message_id=2),
        smartapp_request(
            message_name="MESSAGE_TO_SKILL",
            text="Для чего парацетамол",
            message_id=3,
        ),
        smartapp_request(
            message_name="MESSAGE_TO_SKILL",
            text="Что мне принимать от давления?",
            message_id=4,
        ),
        smartapp_request(message_name="MESSAGE_TO_SKILL", text="Выход", message_id=5),
    ]

    for request in requests:
        response = client.post("/api/v1/sber/webhook", json=request)
        body = response.json()

        assert response.status_code == 200
        assert body["messageName"] == "ANSWER_TO_USER"
        assert body["messageId"] == request["messageId"]
        assert body["payload"]["pronounceTextType"] in {
            "application/text",
            "application/ssml",
        }
        assert isinstance(body["payload"]["auto_listening"], bool)
        assert isinstance(body["payload"]["finished"], bool)
        assert_no_nulls_or_newlines(body)


def test_help_unknown_and_prompt_scenarios_are_not_dead_ends(tmp_path):
    client = build_client(tmp_path)

    help_response = client.post(
        "/api/v1/sber/webhook",
        json=smartapp_request(message_name="MESSAGE_TO_SKILL", text="Помощь", message_id=10),
    ).json()
    assert help_response["payload"]["suggestions"]["buttons"]
    assert help_response["payload"]["items"][1]["card"]["cells"]

    unknown_response = client.post(
        "/api/v1/sber/webhook",
        json=smartapp_request(
            message_name="MESSAGE_TO_SKILL",
            text="непонятная команда",
            message_id=11,
        ),
    ).json()
    assert unknown_response["payload"]["suggestions"]["buttons"]
    assert "что можно сделать" in unknown_response["payload"]["items"][1]["card"]["cells"][0]["content"]["text"].lower()

    prompt_response = client.post(
        "/api/v1/sber/webhook",
        json=smartapp_request(
            message_name="MESSAGE_TO_SKILL",
            text="Добавь лекарство",
            message_id=12,
        ),
    ).json()
    assert prompt_response["payload"]["auto_listening"] is True
    assert prompt_response["payload"]["suggestions"]["buttons"]


def test_server_action_text_from_frontend_is_handled_e2e(tmp_path):
    client = build_client(tmp_path)
    schedule_time = (
        datetime.now().replace(second=0, microsecond=0) - timedelta(minutes=1)
    ).strftime("%H:%M")

    add_response = client.post(
        "/api/v1/sber/webhook",
        json=smartapp_request(
            message_name="MESSAGE_TO_SKILL",
            text=f"Напомни принимать ибупрофен каждый день в {schedule_time} без курса",
            message_id=20,
        ),
    )
    assert add_response.status_code == 200
    assert client.post("/api/v1/dev/scan-reminders").json()["created_notifications"] >= 1

    confirm = client.post(
        "/api/v1/sber/webhook",
        json=smartapp_request(
            message_name="SERVER_ACTION",
            server_action_text="Принял ибупрофен",
            message_id=21,
        ),
    ).json()
    assert "подтверждён" in confirm["payload"]["items"][0]["bubble"]["text"].lower()


def test_visible_demo_assets_do_not_use_protected_sber_brands():
    visible_paths = [
        Path("frontend/index.html"),
        Path("frontend/app.js"),
        Path("frontend/styles.css"),
        Path("data/pharmacies.json"),
        Path("data/drug_reference.json"),
    ]
    banned_terms = [
        "СберАптека",
        "Салют",
        "Sber",
        "Salute",
        "Афина",
        "Джой",
    ]

    for path in visible_paths:
        content = path.read_text(encoding="utf-8")
        for term in banned_terms:
            assert term not in content, f"{term!r} found in {path}"
