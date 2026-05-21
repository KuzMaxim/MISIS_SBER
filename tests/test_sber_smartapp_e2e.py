from __future__ import annotations

from datetime import datetime, timedelta

from fastapi.testclient import TestClient

from app.main import create_app
from app.utils import local_now


def build_client(tmp_path):
    app = create_app(state_file=tmp_path / "runtime_state.json", start_scheduler=False)
    return TestClient(app)


def smartapp_request(
    *,
    message_name: str,
    text: str | None = None,
    intent: str | None = None,
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
        "intent": intent,
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


def test_sber_first_launch_starts_with_empty_setup_screen(tmp_path):
    client = build_client(tmp_path)

    response = client.post(
        "/api/v1/sber/webhook",
        json=smartapp_request(
            message_name="RUN_APP",
            has_screen=True,
            new_session=True,
            user_id="new-smart-user",
        ),
    )
    body = response.json()
    visible_text = " ".join(
        cell["content"]["text"]
        for cell in body["payload"]["items"][1]["card"]["cells"]
    )

    assert response.status_code == 200
    assert "Расписание пока пустое" in body["payload"]["items"][0]["bubble"]["text"]
    assert "Список лекарств пока пуст" in visible_text
    assert "Добавь лекарство" in [
        button["title"] for button in body["payload"]["suggestions"]["buttons"]
    ]
    assert client.get("/api/v1/medications/new-smart-user").json() == []
    assert not any(name in visible_text for name in ["Аспирин", "Ибупрофен", "Парацетамол"])


def test_sber_root_webhook_alias_accepts_smartapp_requests(tmp_path):
    client = build_client(tmp_path)

    response = client.post(
        "/",
        json=smartapp_request(message_name="RUN_APP", has_screen=True),
    )

    assert response.status_code == 200
    assert response.json()["messageName"] == "ANSWER_TO_USER"


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
        json=smartapp_request(
            message_name="MESSAGE_TO_SKILL",
            text="Аспирин",
            intent=step1["payload"]["intent"],
            message_id=2,
        ),
    ).json()
    assert "Когда принимать" in step2["payload"]["items"][0]["bubble"]["text"]

    step3 = client.post(
        "/api/v1/sber/webhook",
        json=smartapp_request(
            message_name="MESSAGE_TO_SKILL",
            text="Каждый день в 9 утра",
            intent=step2["payload"]["intent"],
            message_id=3,
        ),
    ).json()
    assert "Сколько дней курс" in step3["payload"]["items"][0]["bubble"]["text"]

    step4 = client.post(
        "/api/v1/sber/webhook",
        json=smartapp_request(
            message_name="MESSAGE_TO_SKILL",
            text="7 дней",
            intent=step3["payload"]["intent"],
            message_id=4,
        ),
    ).json()
    assert "расписание" in step4["payload"]["items"][0]["bubble"]["text"].lower()
    assert "добавлен" in step4["payload"]["items"][0]["bubble"]["text"].lower()
    assert step4["payload"]["items"][1]["card"]["cells"][1]["content"]["text"] == "Время: 09:00"

    meds = client.get("/api/v1/medications/smart-user").json()
    assert len(meds) == 1
    assert meds[0]["name"] == "Аспирин"


def test_sber_moderation_time_phrases_are_recognized_e2e(tmp_path):
    client = build_client(tmp_path)

    for index, time_phrase in enumerate(
        ["Каждый день в 9 утра", "В 9 утра", "каждый день 9 утра", "в девять утра"],
        start=1,
    ):
        user_id = f"time-phrase-user-{index}"
        step1 = client.post(
            "/api/v1/sber/webhook",
            json=smartapp_request(
                message_name="MESSAGE_TO_SKILL",
                text="Добавь лекарство",
                message_id=index * 10 + 1,
                user_id=user_id,
            ),
        ).json()
        step2 = client.post(
            "/api/v1/sber/webhook",
            json=smartapp_request(
                message_name="MESSAGE_TO_SKILL",
                text="Аспирин",
                intent=step1["payload"]["intent"],
                message_id=index * 10 + 2,
                user_id=user_id,
            ),
        ).json()
        step3 = client.post(
            "/api/v1/sber/webhook",
            json=smartapp_request(
                message_name="MESSAGE_TO_SKILL",
                text=time_phrase,
                intent=step2["payload"]["intent"],
                message_id=index * 10 + 3,
                user_id=user_id,
            ),
        ).json()

        bubble_text = step3["payload"]["items"][0]["bubble"]["text"]
        assert "Не удалось распознать время" not in bubble_text
        assert "Сколько дней курс" in bubble_text

        step4 = client.post(
            "/api/v1/sber/webhook",
            json=smartapp_request(
                message_name="MESSAGE_TO_SKILL",
                text="7 дней",
                intent=step3["payload"]["intent"],
                message_id=index * 10 + 4,
                user_id=user_id,
            ),
        ).json()
        assert "09:00" in step4["payload"]["items"][0]["bubble"]["text"]
        assert client.get(f"/api/v1/medications/{user_id}").json()[0]["schedule_times"] == [
            "09:00"
        ]


def test_sber_repeated_add_command_is_not_saved_as_medication_name(tmp_path):
    client = build_client(tmp_path)
    user_id = "repeat-add-user"

    step1 = client.post(
        "/api/v1/sber/webhook",
        json=smartapp_request(
            message_name="MESSAGE_TO_SKILL",
            text="Добавь лекарство",
            message_id=1,
            user_id=user_id,
        ),
    ).json()
    step2 = client.post(
        "/api/v1/sber/webhook",
        json=smartapp_request(
            message_name="MESSAGE_TO_SKILL",
            text="Добавь лекарство",
            intent=step1["payload"]["intent"],
            message_id=2,
            user_id=user_id,
        ),
    ).json()

    assert "Назовите препарат" in step2["payload"]["items"][0]["bubble"]["text"]
    assert client.get(f"/api/v1/medications/{user_id}").json() == []

    step3 = client.post(
        "/api/v1/sber/webhook",
        json=smartapp_request(
            message_name="MESSAGE_TO_SKILL",
            text="Аспирин",
            intent=step2["payload"]["intent"],
            message_id=3,
            user_id=user_id,
        ),
    ).json()
    step4 = client.post(
        "/api/v1/sber/webhook",
        json=smartapp_request(
            message_name="MESSAGE_TO_SKILL",
            text="Каждый день в 9 утра",
            intent=step3["payload"]["intent"],
            message_id=4,
            user_id=user_id,
        ),
    ).json()
    client.post(
        "/api/v1/sber/webhook",
        json=smartapp_request(
            message_name="MESSAGE_TO_SKILL",
            text="7 дней",
            intent=step4["payload"]["intent"],
            message_id=5,
            user_id=user_id,
        ),
    )

    list_response = client.post(
        "/api/v1/sber/webhook",
        json=smartapp_request(
            message_name="MESSAGE_TO_SKILL",
            text="Показать лекарства",
            message_id=6,
            user_id=user_id,
        ),
    ).json()
    list_text = list_response["payload"]["items"][0]["bubble"]["text"].lower()
    meds = client.get(f"/api/v1/medications/{user_id}").json()

    assert len(meds) == 1
    assert meds[0]["name"] == "Аспирин"
    assert "1 лекарство" in list_text
    assert "Аспирин — 09:00" in list_response["payload"]["items"][0]["bubble"]["text"]
    assert "например" not in list_text
    assert "добавь лекар" not in list_text


def test_sber_course_words_and_canvas_state_update_e2e(tmp_path):
    client = build_client(tmp_path)
    user_id = "canvas-state-user"

    step1 = client.post(
        "/api/v1/sber/webhook",
        json=smartapp_request(
            message_name="MESSAGE_TO_SKILL",
            text="Добавь лекарство",
            message_id=1,
            user_id=user_id,
        ),
    ).json()
    step2 = client.post(
        "/api/v1/sber/webhook",
        json=smartapp_request(
            message_name="MESSAGE_TO_SKILL",
            text="Аспирин",
            intent=step1["payload"]["intent"],
            message_id=2,
            user_id=user_id,
        ),
    ).json()
    step3 = client.post(
        "/api/v1/sber/webhook",
        json=smartapp_request(
            message_name="MESSAGE_TO_SKILL",
            text="Каждый день в 9 утра",
            intent=step2["payload"]["intent"],
            message_id=3,
            user_id=user_id,
        ),
    ).json()
    step4 = client.post(
        "/api/v1/sber/webhook",
        json=smartapp_request(
            message_name="MESSAGE_TO_SKILL",
            text="семь дней",
            intent=step3["payload"]["intent"],
            message_id=4,
            user_id=user_id,
        ),
    ).json()

    command_items = [
        item["command"]
        for item in step4["payload"]["items"]
        if "command" in item and item["command"]["type"] == "smart_app_data"
    ]
    assert "добавлен" in step4["payload"]["items"][0]["bubble"]["text"].lower()
    assert command_items
    assert command_items[0]["smart_app_data"]["type"] == "health_state"
    assert command_items[0]["smart_app_data"]["payload"]["medications"] == [
        {
            "name": "Аспирин",
            "schedule_times": ["09:00"],
            "next_time": "09:00",
            "course_days": 7,
        }
    ]

    run_app = client.post(
        "/api/v1/sber/webhook",
        json=smartapp_request(
            message_name="RUN_APP",
            has_screen=True,
            new_session=True,
            user_id=user_id,
        ),
    ).json()
    assert "В расписании 1 лекарство: Аспирин — 09:00, курс 7 дней." in run_app[
        "payload"
    ]["items"][0]["bubble"]["text"]
    assert run_app["payload"]["items"][1]["card"]["cells"][0]["content"]["text"] == "Ваше расписание"


def test_sber_medication_list_is_ordered_by_next_intake(tmp_path):
    client = build_client(tmp_path)
    user_id = "ordered-user"
    now = local_now().replace(second=0, microsecond=0)
    near_time = (now + timedelta(hours=9)).strftime("%H:%M")
    far_time = (now - timedelta(hours=5)).strftime("%H:%M")

    for name, schedule_time in [
        ("Дальний препарат", far_time),
        ("Ближайший препарат", near_time),
    ]:
        response = client.post(
            "/api/v1/medications",
            json={
                "user_id": user_id,
                "name": name,
                "schedule_times": [schedule_time],
                "course_days": 7,
                "started_at": now.date().isoformat(),
            },
        )
        assert response.status_code == 200

    list_response = client.post(
        "/api/v1/sber/webhook",
        json=smartapp_request(
            message_name="MESSAGE_TO_SKILL",
            text="Показать лекарства",
            message_id=1,
            user_id=user_id,
        ),
    ).json()
    bubble_text = list_response["payload"]["items"][0]["bubble"]["text"]
    command_items = [
        item["command"]
        for item in list_response["payload"]["items"]
        if "command" in item and item["command"]["type"] == "smart_app_data"
    ]

    assert bubble_text.index("Ближайший препарат") < bubble_text.index("Дальний препарат")
    assert command_items[0]["smart_app_data"]["payload"]["medications"][0]["name"] == "Ближайший препарат"


def test_sber_pharmacy_and_info_buttons_ask_for_drug_name(tmp_path):
    client = build_client(tmp_path)
    user_id = "prompt-user"

    pharmacy_prompt = client.post(
        "/api/v1/sber/webhook",
        json=smartapp_request(
            message_name="MESSAGE_TO_SKILL",
            text="Найти аптеку",
            message_id=1,
            user_id=user_id,
        ),
    ).json()
    assert "Назовите препарат" in pharmacy_prompt["payload"]["items"][0]["bubble"]["text"]

    pharmacy_result = client.post(
        "/api/v1/sber/webhook",
        json=smartapp_request(
            message_name="MESSAGE_TO_SKILL",
            text="Ибупрофен",
            message_id=2,
            user_id=user_id,
        ),
    ).json()
    assert "самая низкая цена" in pharmacy_result["payload"]["items"][0]["bubble"]["text"]

    info_prompt = client.post(
        "/api/v1/sber/webhook",
        json=smartapp_request(
            message_name="MESSAGE_TO_SKILL",
            text="Справка о препарате",
            message_id=3,
            user_id=user_id,
        ),
    ).json()
    assert "Назовите препарат" in info_prompt["payload"]["items"][0]["bubble"]["text"]

    info_result = client.post(
        "/api/v1/sber/webhook",
        json=smartapp_request(
            message_name="MESSAGE_TO_SKILL",
            text="Парацетамол",
            message_id=4,
            user_id=user_id,
        ),
    ).json()
    assert info_result["payload"]["items"][0]["bubble"]["text"].startswith("По инструкции")


def test_sber_previous_response_intent_does_not_break_multistep_flow(tmp_path):
    client = build_client(tmp_path)

    step1 = client.post(
        "/api/v1/sber/webhook",
        json=smartapp_request(message_name="MESSAGE_TO_SKILL", text="Добавь лекарство", message_id=1),
    ).json()
    previous_intent = step1["payload"]["intent"]
    assert previous_intent == "ДобавитьЛекарство"

    step2 = client.post(
        "/api/v1/sber/webhook",
        json=smartapp_request(
            message_name="MESSAGE_TO_SKILL",
            text="Аспирин",
            intent=previous_intent,
            message_id=2,
        ),
    ).json()

    assert "Когда принимать" in step2["payload"]["items"][0]["bubble"]["text"]


def test_sber_one_phrase_moderation_add_without_course(tmp_path):
    client = build_client(tmp_path)

    response = client.post(
        "/api/v1/sber/webhook",
        json=smartapp_request(
            message_name="MESSAGE_TO_SKILL",
            text="Напомни принимать ибупрофен каждый день в 9 утра без курса",
            message_id=1,
        ),
    )
    body = response.json()

    assert response.status_code == 200
    assert "добавлен" in body["payload"]["items"][0]["bubble"]["text"].lower()
    assert "09:00" in body["payload"]["items"][0]["bubble"]["text"]
    assert any(
        cell["content"]["text"] == "Курс: не задан"
        for cell in body["payload"]["items"][1]["card"]["cells"]
    )


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
