from __future__ import annotations

from html import escape

from app.safety import SAFE_DISCLAIMER
from app.schemas import SmartAppRequest, VoiceRequest, VoiceResponse
from app.utils import single_line_text


class SmartAppService:
    def __init__(self, dialog_service, medication_service):
        self.dialog_service = dialog_service
        self.medication_service = medication_service

    def handle(self, request: SmartAppRequest) -> dict | None:
        if request.messageName == "CLOSE_APP":
            return None

        user_id = self._extract_user_id(request)
        utterance = self._extract_utterance(request)
        has_screen = self._has_screen(request)
        can_speak = self._can_speak(request)

        if request.messageName == "RUN_APP" and not utterance:
            self.medication_service.ensure_user(user_id)
            voice_response = self._welcome_response()
        elif request.payload.new_session and not utterance:
            self.medication_service.ensure_user(user_id)
            voice_response = self._welcome_response()
        else:
            voice_response = self.dialog_service.handle(
                VoiceRequest(
                    user_id=user_id,
                    utterance=utterance,
                    # In SmartApp API this is the context value returned by the
                    # previous response, not a freshly classified user intent.
                    intent=None,
                )
            )

        return self._build_response(
            request,
            voice_response,
            has_screen=has_screen,
            can_speak=can_speak,
        )

    def _extract_user_id(self, request: SmartAppRequest) -> str:
        return str(request.uuid.sub or request.uuid.userId)

    @staticmethod
    def _extract_utterance(request: SmartAppRequest) -> str | None:
        if request.payload.message and request.payload.message.original_text:
            return request.payload.message.original_text
        if request.payload.server_action and request.payload.server_action.parameters:
            return request.payload.server_action.parameters.get("text")
        return None

    @staticmethod
    def _has_screen(request: SmartAppRequest) -> bool:
        device_screen = (
            request.payload.device.capabilities.screen.available
            if request.payload.device
            and request.payload.device.capabilities
            and request.payload.device.capabilities.screen
            and request.payload.device.capabilities.screen.available is not None
            else None
        )
        feature_screen = (
            request.payload.meta.features.screen.enabled
            if request.payload.meta
            and request.payload.meta.features
            and request.payload.meta.features.screen
            and request.payload.meta.features.screen.enabled is not None
            else None
        )
        return bool(device_screen or feature_screen)

    @staticmethod
    def _can_speak(request: SmartAppRequest) -> bool:
        speak_available = (
            request.payload.device.capabilities.speak.available
            if request.payload.device
            and request.payload.device.capabilities
            and request.payload.device.capabilities.speak
            and request.payload.device.capabilities.speak.available is not None
            else True
        )
        return bool(speak_available)

    @staticmethod
    def _welcome_response() -> VoiceResponse:
        return VoiceResponse(
            text=(
                "Я помогу не забывать о лекарствах: добавлю препарат в расписание, "
                "подскажу день курса, дам справку по инструкции и помогу найти аптеку."
            ),
            intent="Помощь",
            disclaimer=SAFE_DISCLAIMER,
            suggestions=[
                "Добавь лекарство",
                "Для чего парацетамол",
                "Где купить ибупрофен",
            ],
            auto_listening=True,
            finished=False,
            audio_cue="welcome",
            emotion="zainteresovannost",
            screen_title="Помощник здоровья",
            screen_lines=[
                "Добавление лекарства",
                "Напоминания и подтверждение приема",
                "Курс лечения",
                "Справка по инструкции",
                "Поиск аптек",
                SAFE_DISCLAIMER,
            ],
            speak_disclaimer=True,
        )

    def _build_response(
        self,
        request: SmartAppRequest,
        voice_response: VoiceResponse,
        *,
        has_screen: bool,
        can_speak: bool,
    ) -> dict:
        bubble_text = single_line_text(voice_response.text)
        speak_text = bubble_text
        if voice_response.speak_disclaimer and voice_response.disclaimer:
            speak_text = f"{bubble_text} {single_line_text(voice_response.disclaimer)}"

        payload = {
            "pronounceText": (
                self._build_ssml(speak_text, voice_response.audio_cue)
                if can_speak
                else speak_text
            ),
            "pronounceTextType": "application/ssml" if can_speak else "application/text",
            "items": self._build_items(voice_response, bubble_text, has_screen),
            "suggestions": {"buttons": self._build_buttons(voice_response.suggestions)},
            "auto_listening": voice_response.auto_listening,
            "finished": voice_response.finished,
            "intent": voice_response.intent or "ROOT",
        }
        if voice_response.emotion:
            payload["emotion"] = {"emotionId": voice_response.emotion}

        return self._compact(
            {
                "sessionId": request.sessionId,
                "messageId": request.messageId,
                "uuid": request.uuid.model_dump(exclude_none=True),
                "messageName": "ANSWER_TO_USER",
                "payload": payload,
            }
        )

    def _build_items(
        self,
        voice_response: VoiceResponse,
        bubble_text: str,
        has_screen: bool,
    ) -> list[dict]:
        items = [{"bubble": {"text": bubble_text, "markdown": True}}]
        if not has_screen:
            return items

        screen_title = single_line_text(voice_response.screen_title or bubble_text)
        screen_lines = [
            single_line_text(line)
            for line in voice_response.screen_lines
            if single_line_text(line)
        ]
        if voice_response.disclaimer and voice_response.disclaimer not in screen_lines:
            if voice_response.intent in {"СправкаОПрепарате", "БезопасныйОтказ", "Помощь"}:
                screen_lines.append(single_line_text(voice_response.disclaimer))

        cells = [
            self._text_cell(screen_title, typeface="headline3"),
        ]
        for line in screen_lines[:6]:
            cells.append(
                self._text_cell(
                    line,
                    typeface="body2",
                    text_color="secondary" if "не заменяет консультацию врача" in line.lower() else "default",
                )
            )

        items.append(
            {
                "card": {
                    "type": "list_card",
                    "paddings": {
                        "top": "8x",
                        "bottom": "8x",
                    },
                    "cells": cells,
                }
            }
        )
        return items

    @staticmethod
    def _text_cell(
        text: str,
        *,
        typeface: str,
        text_color: str = "default",
    ) -> dict:
        return {
            "type": "text_cell_view",
            "content": {
                "text": single_line_text(text),
                "typeface": typeface,
                "text_color": text_color,
                "max_lines": 0,
            },
            "paddings": {
                "left": "8x",
                "right": "8x",
                "top": "6x",
                "bottom": "2x",
            },
        }

    @staticmethod
    def _build_buttons(suggestions: list[str]) -> list[dict]:
        buttons = []
        seen: set[str] = set()
        for title in suggestions:
            clean_title = single_line_text(title)
            if not clean_title or clean_title in seen:
                continue
            seen.add(clean_title)
            buttons.append(
                {
                    "title": clean_title,
                    "actions": [
                        {
                            "type": "text",
                            "text": clean_title,
                            "should_send_to_backend": True,
                        }
                    ],
                }
            )
        return buttons[:4]

    @staticmethod
    def _build_ssml(text: str, audio_cue: str | None) -> str:
        cue_map = {
            "welcome": ('<audio text="sm-sounds-human-cheer-1">отлично</audio>',),
            "success": ('<audio text="ура!">отлично</audio>',),
            "prompt": ('<audio text="кхм-кхм">внимание</audio>',),
            "info": ('<audio text="угу">хорошо</audio>',),
            "warning": ('<audio text="ой">внимание</audio>',),
        }
        prefix = cue_map.get(audio_cue, ("",))[0]
        return f"<speak>{prefix}{escape(single_line_text(text))}</speak>"

    @staticmethod
    def _compact(value):
        if isinstance(value, dict):
            result = {}
            for key, item in value.items():
                compacted = SmartAppService._compact(item)
                if compacted is None:
                    continue
                result[key] = compacted
            return result
        if isinstance(value, list):
            return [SmartAppService._compact(item) for item in value if item is not None]
        return value
