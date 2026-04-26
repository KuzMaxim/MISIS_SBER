from __future__ import annotations

from datetime import date

from app.nlu import extract_course_details, parse_utterance
from app.safety import SAFE_DISCLAIMER, medical_refusal_text, requires_medical_refusal
from app.schemas import MedicationCreate, VoiceRequest, VoiceResponse
from app.storage import JsonStorage
from app.utils import format_schedule_times, normalize_text, parse_time_fragment


class DialogService:
    def __init__(
        self,
        storage: JsonStorage,
        medication_service,
        drug_info_service,
        pharmacy_service,
    ):
        self.storage = storage
        self.medication_service = medication_service
        self.drug_info_service = drug_info_service
        self.pharmacy_service = pharmacy_service

    def handle(self, request: VoiceRequest) -> VoiceResponse:
        if requires_medical_refusal(request.utterance):
            return VoiceResponse(
                text=medical_refusal_text(),
                intent="БезопасныйОтказ",
                disclaimer=SAFE_DISCLAIMER,
                suggestions=["Для чего парацетамол", "Добавь лекарство", "Помощь"],
                audio_cue="warning",
                emotion="bespokoistvo",
                screen_title="Только справочная информация",
                screen_lines=[
                    "Я не ставлю диагнозы и не назначаю лечение.",
                    SAFE_DISCLAIMER,
                ],
                speak_disclaimer=True,
            )

        if request.intent:
            return self._dispatch(
                request.user_id,
                request.intent,
                request.slots,
                utterance=request.utterance,
            )

        session = self._get_session(request.user_id)
        if session and request.utterance:
            return self._continue_session(request.user_id, session, request.utterance)

        parsed = parse_utterance(request.utterance or "")
        return self._dispatch(
            request.user_id,
            parsed.intent,
            parsed.slots,
            utterance=request.utterance,
        )

    def _get_session(self, user_id: str) -> dict | None:
        state = self.storage.read()
        return state["dialog_sessions"].get(user_id)

    def _set_session(self, user_id: str, session: dict | None) -> None:
        def mutate(state: dict) -> None:
            if session is None:
                state["dialog_sessions"].pop(user_id, None)
                return
            state["dialog_sessions"][user_id] = session

        self.storage.transaction(mutate)

    def _continue_session(self, user_id: str, session: dict, utterance: str) -> VoiceResponse:
        step = session["step"]
        draft = session["draft"]

        if step == "awaiting_name":
            draft["name"] = utterance.strip()
            session["step"] = "awaiting_time"
            self._set_session(user_id, session)
            return VoiceResponse(
                text="Когда принимать? Например: каждый день в 9 утра.",
                intent="ДобавитьЛекарство",
                suggestions=["Каждый день в 9 утра", "В 8 вечера", "Помощь"],
                auto_listening=True,
                audio_cue="prompt",
                emotion="zhdu_otvet",
                screen_title="Настройка расписания",
                screen_lines=[
                    f"Препарат: {draft['name']}",
                    "Назовите время приема.",
                ],
            )

        if step == "awaiting_time":
            schedule_time = parse_time_fragment(utterance)
            if not schedule_time:
                return VoiceResponse(
                    text="Не удалось распознать время. Скажите, например: в 9 утра.",
                    intent="ДобавитьЛекарство",
                    suggestions=["В 9 утра", "В 8 вечера", "Помощь"],
                    auto_listening=True,
                    audio_cue="warning",
                    emotion="zadumalsa",
                    screen_title="Не удалось распознать время",
                    screen_lines=[
                        "Скажите время в формате: в 9 утра.",
                    ],
                )
            draft["schedule_times"] = [schedule_time]
            session["step"] = "awaiting_course"
            self._set_session(user_id, session)
            return VoiceResponse(
                text="Сколько дней курс? Если курс не задан, скажите: без курса.",
                intent="ДобавитьЛекарство",
                suggestions=["7 дней", "30 дней", "Без курса"],
                auto_listening=True,
                audio_cue="prompt",
                emotion="zhdu_otvet",
                screen_title="Настройка курса",
                screen_lines=[
                    f"Препарат: {draft['name']}",
                    f"Время: {schedule_time}",
                    "Назовите длительность курса.",
                ],
            )

        if step == "awaiting_course":
            course_details = extract_course_details(utterance)
            if not course_details["course_provided"]:
                return VoiceResponse(
                    text="Скажите число дней курса или фразу: без курса.",
                    intent="ДобавитьЛекарство",
                    suggestions=["7 дней", "30 дней", "Без курса"],
                    auto_listening=True,
                    audio_cue="warning",
                    emotion="zadumalsa",
                    screen_title="Нужна длительность курса",
                    screen_lines=[
                        "Скажите число дней или фразу: без курса.",
                    ],
                )
            draft["course_days"] = course_details["course_days"]
            response = self._create_medication_from_draft(user_id, draft)
            self._set_session(user_id, None)
            return response

        self._set_session(user_id, None)
        return VoiceResponse(
            text="Давайте начнём заново. Скажите: добавь лекарство.",
            suggestions=["Добавь лекарство", "Помощь"],
            auto_listening=True,
            audio_cue="warning",
            emotion="zadumalsa",
            screen_title="Начнем заново",
            screen_lines=["Скажите: добавь лекарство."],
        )

    def _dispatch(
        self,
        user_id: str,
        intent: str,
        slots: dict,
        *,
        utterance: str | None = None,
    ) -> VoiceResponse:
        if intent == "Помощь":
            return self._help_response()

        if intent == "Завершить":
            return VoiceResponse(
                text="Берегите себя. Если понадобится, я снова помогу с лекарствами и напоминаниями.",
                intent=intent,
                suggestions=[],
                auto_listening=False,
                finished=True,
                audio_cue="success",
                emotion="radost",
                screen_title="До встречи",
                screen_lines=[
                    "Я помогу снова, когда вы меня откроете.",
                ],
            )

        if intent == "ПоказатьЛекарства":
            return self._show_medications(user_id)

        if intent == "ДобавитьЛекарство":
            return self._handle_add_medication(user_id, slots)

        if intent == "ПодтвердитьПрием":
            record = self.medication_service.confirm_intake(user_id, slots.get("name"))
            if not record:
                return VoiceResponse(
                    text="Сейчас нет активного напоминания для подтверждения.",
                    suggestions=["Покажи лекарства", "Помощь"],
                    audio_cue="warning",
                    emotion="zadumalsa",
                    screen_title="Нет активного напоминания",
                    screen_lines=["Сначала дождитесь напоминания или проверьте список лекарств."],
                )
            return VoiceResponse(
                text=f"Приём препарата {record['medication_name']} подтверждён.",
                intent=intent,
                suggestions=["Покажи лекарства", "Помощь"],
                audio_cue="success",
                emotion="ok_prinyato",
                screen_title="Прием подтвержден",
                screen_lines=[
                    f"Препарат: {record['medication_name']}",
                    "Статус: принято",
                ],
            )

        if intent == "ОтложитьНапоминание":
            record = self.medication_service.snooze_intake(
                user_id,
                slots.get("minutes", 10),
                slots.get("name"),
            )
            if not record:
                return VoiceResponse(
                    text="Не удалось найти активное напоминание для переноса.",
                    suggestions=["Покажи лекарства", "Помощь"],
                    audio_cue="warning",
                    emotion="zadumalsa",
                    screen_title="Нечего переносить",
                    screen_lines=["Активное напоминание сейчас не найдено."],
                )
            return VoiceResponse(
                text=(
                    f"Напоминание по препарату {record['medication_name']} "
                    f"отложено на {slots.get('minutes', 10)} минут."
                ),
                intent=intent,
                suggestions=["Принял", "Покажи лекарства", "Помощь"],
                audio_cue="success",
                emotion="ok_prinyato",
                screen_title="Напоминание перенесено",
                screen_lines=[
                    f"Препарат: {record['medication_name']}",
                    f"Отложено на {slots.get('minutes', 10)} минут",
                ],
            )

        if intent == "СпроситьОКурсе":
            status = self.medication_service.get_course_status(user_id, slots.get("name"))
            return VoiceResponse(
                text=status["message"],
                intent=intent,
                data=status,
                suggestions=["Покажи лекарства", "Добавь лекарство", "Помощь"],
                audio_cue="info",
                emotion="zainteresovannost",
                screen_title=f"Курс: {status['medication_name'] or 'лекарство'}",
                screen_lines=[
                    status["message"],
                ],
            )

        if intent == "ПоискАптеки":
            name = slots.get("name")
            if not name:
                return VoiceResponse(
                    text="Назовите препарат, который нужно найти в аптеке.",
                    suggestions=["Где купить ибупрофен", "Где купить парацетамол", "Помощь"],
                    auto_listening=True,
                    audio_cue="prompt",
                    emotion="zhdu_otvet",
                    screen_title="Поиск в аптеках",
                    screen_lines=["Назовите препарат."],
                )
            result = self.pharmacy_service.search(name)
            if not result["results"]:
                text = f"Не нашла аптек с препаратом {name} в локальном каталоге."
                screen_lines = [text]
            else:
                best = result["results"][0]
                text = (
                    f"Самый выгодный вариант: {best['pharmacy_name']}, "
                    f"{best['address']}, цена {best['price']} рублей."
                )
                screen_lines = [
                    f"{best['pharmacy_name']} — {best['price']} ₽",
                    f"{best['address']}",
                ]
                if len(result["results"]) > 1:
                    for item in result["results"][1:3]:
                        screen_lines.append(f"{item['pharmacy_name']} — {item['price']} ₽")
            return VoiceResponse(
                text=text,
                intent=intent,
                disclaimer=result["disclaimer"],
                data=result,
                suggestions=["Где купить парацетамол", "Покажи лекарства", "Помощь"],
                audio_cue="info",
                emotion="zainteresovannost",
                screen_title=f"Аптеки: {name}",
                screen_lines=screen_lines,
            )

        if intent == "СправкаОПрепарате":
            name = slots.get("name")
            if not name:
                return VoiceResponse(
                    text="Назовите препарат, о котором нужна справка.",
                    suggestions=["Для чего парацетамол", "Для чего ибупрофен", "Помощь"],
                    auto_listening=True,
                    audio_cue="prompt",
                    emotion="zhdu_otvet",
                    screen_title="Справка о препарате",
                    screen_lines=["Назовите препарат."],
                )
            info = self.drug_info_service.get_info(name)
            contra = ""
            screen_lines = [info["answer"]]
            if info["contraindications"]:
                contra = " Противопоказания по инструкции: " + ", ".join(info["contraindications"]) + "."
                screen_lines.append(
                    "Противопоказания: " + ", ".join(info["contraindications"][:3])
                )
            screen_lines.append(info["disclaimer"])
            return VoiceResponse(
                text=info["answer"] + contra,
                intent=intent,
                disclaimer=info["disclaimer"],
                data=info,
                suggestions=["Какие противопоказания у парацетамола", "Добавь лекарство", "Помощь"],
                audio_cue="info",
                emotion="zainteresovannost",
                screen_title=f"Справка: {name}",
                screen_lines=screen_lines,
                speak_disclaimer=True,
            )

        if intent == "Неизвестно":
            if utterance and normalize_text(utterance) in {"принял", "приняла"}:
                record = self.medication_service.confirm_intake(user_id)
                if record:
                    return VoiceResponse(
                        text=f"Приём препарата {record['medication_name']} подтверждён.",
                        intent="ПодтвердитьПрием",
                        suggestions=["Покажи лекарства", "Помощь"],
                        audio_cue="success",
                        emotion="ok_prinyato",
                        screen_title="Прием подтвержден",
                        screen_lines=[
                            f"Препарат: {record['medication_name']}",
                            "Статус: принято",
                        ],
                    )
            return VoiceResponse(
                text=(
                    "Я могу помочь с напоминаниями о лекарствах, курсом лечения, "
                    "справочной информацией о препаратах и поиском аптек."
                ),
                suggestions=["Добавь лекарство", "Помощь", "Покажи лекарства"],
                audio_cue="warning",
                emotion="zadumalsa",
                screen_title="Что можно сделать",
                screen_lines=[
                    "Добавить лекарство",
                    "Узнать день курса",
                    "Получить справку по инструкции",
                    "Найти аптеку",
                ],
            )

        return VoiceResponse(
            text="Этот сценарий пока не поддерживается в текущей версии навыка.",
            suggestions=["Помощь", "Добавь лекарство"],
            audio_cue="warning",
            emotion="zadumalsa",
            screen_title="Сценарий недоступен",
            screen_lines=["Попробуйте команду: добавь лекарство."],
        )

    def _handle_add_medication(self, user_id: str, slots: dict) -> VoiceResponse:
        name = slots.get("name")
        schedule_times = slots.get("schedule_times") or []
        course_provided = slots.get("course_provided", False)

        if not name:
            self._set_session(
                user_id,
                {"intent": "ДобавитьЛекарство", "step": "awaiting_name", "draft": {}},
            )
            return VoiceResponse(
                text="Как называется препарат?",
                intent="ДобавитьЛекарство",
                suggestions=["Аспирин", "Ибупрофен", "Парацетамол"],
                auto_listening=True,
                audio_cue="prompt",
                emotion="zhdu_otvet",
                screen_title="Добавление лекарства",
                screen_lines=["Назовите препарат."],
            )

        if not schedule_times:
            self._set_session(
                user_id,
                {
                    "intent": "ДобавитьЛекарство",
                    "step": "awaiting_time",
                    "draft": {"name": name},
                },
            )
            return VoiceResponse(
                text="Когда принимать? Например: каждый день в 9 утра.",
                intent="ДобавитьЛекарство",
                suggestions=["Каждый день в 9 утра", "В 8 вечера", "Помощь"],
                auto_listening=True,
                audio_cue="prompt",
                emotion="zhdu_otvet",
                screen_title="Настройка расписания",
                screen_lines=[
                    f"Препарат: {name}",
                    "Назовите время приема.",
                ],
            )

        if not course_provided:
            self._set_session(
                user_id,
                {
                    "intent": "ДобавитьЛекарство",
                    "step": "awaiting_course",
                    "draft": {"name": name, "schedule_times": schedule_times},
                },
            )
            return VoiceResponse(
                text="Сколько дней курс? Если курс не задан, скажите: без курса.",
                intent="ДобавитьЛекарство",
                suggestions=["7 дней", "30 дней", "Без курса"],
                auto_listening=True,
                audio_cue="prompt",
                emotion="zhdu_otvet",
                screen_title="Настройка курса",
                screen_lines=[
                    f"Препарат: {name}",
                    f"Время: {schedule_times[0]}",
                    "Назовите длительность курса.",
                ],
            )

        draft = {
            "name": name,
            "schedule_times": schedule_times,
            "course_days": slots.get("course_days"),
        }
        return self._create_medication_from_draft(user_id, draft)

    def _create_medication_from_draft(self, user_id: str, draft: dict) -> VoiceResponse:
        payload = MedicationCreate(
            user_id=user_id,
            name=draft["name"],
            schedule_times=draft["schedule_times"],
            course_days=draft.get("course_days"),
            started_at=date.today(),
        )
        medication, _created = self.medication_service.add_or_update_medication(payload)
        return VoiceResponse(
            text=self.medication_service.build_add_message(medication),
            intent="ДобавитьЛекарство",
            data={
                "medication_name": medication["name"],
                "schedule": format_schedule_times(medication["schedule_times"]),
            },
            suggestions=["Покажи лекарства", "Добавь лекарство", "Помощь"],
            audio_cue="success",
            emotion="ok_prinyato",
            screen_title=f"Добавлено: {medication['name']}",
            screen_lines=[
                f"Время: {format_schedule_times(medication['schedule_times'])}",
                (
                    f"Курс: {medication['course_days']} дней"
                    if medication.get("course_days")
                    else "Курс: не задан"
                ),
            ],
        )

    def _help_response(self) -> VoiceResponse:
        return VoiceResponse(
            text=(
                "Я помогу добавить лекарство, напомню о приёме, подскажу день курса, "
                "дам справочную информацию по инструкции и помогу найти аптеку."
            ),
            intent="Помощь",
            disclaimer=SAFE_DISCLAIMER,
            suggestions=[
                "Добавь лекарство",
                "Для чего парацетамол",
                "Где купить ибупрофен",
            ],
            auto_listening=False,
            audio_cue="info",
            emotion="zainteresovannost",
            screen_title="Что умеет навык",
            screen_lines=[
                "Добавление лекарства и расписания",
                "Напоминания и подтверждение приема",
                "Отслеживание курса лечения",
                "Справка по инструкции",
                "Поиск аптек и цен",
                SAFE_DISCLAIMER,
            ],
            speak_disclaimer=True,
        )

    def _show_medications(self, user_id: str) -> VoiceResponse:
        medications = self.medication_service.list_medications(user_id)
        if not medications:
            return VoiceResponse(
                text="У вас пока нет добавленных лекарств.",
                intent="ПоказатьЛекарства",
                suggestions=["Добавь лекарство", "Помощь"],
                audio_cue="info",
                emotion="zadumalsa",
                screen_title="Лекарства не найдены",
                screen_lines=["Скажите: добавь лекарство."],
            )

        lines = []
        for medication in medications[:5]:
            course_part = (
                f", курс {medication['course_days']} дней"
                if medication.get("course_days")
                else ""
            )
            lines.append(
                f"{medication['name']} — {format_schedule_times(medication['schedule_times'])}{course_part}"
            )

        first_name = medications[0]["name"]
        return VoiceResponse(
            text=f"В расписании {len(medications)} лекарств. Например: {first_name}.",
            intent="ПоказатьЛекарства",
            data={"items": medications},
            suggestions=["Добавь лекарство", "Помощь", f"День курса {first_name}"],
            audio_cue="info",
            emotion="zainteresovannost",
            screen_title="Ваше расписание",
            screen_lines=lines,
        )
