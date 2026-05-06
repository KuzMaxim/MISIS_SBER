# Умный помощник здоровья

MVP голосового навыка для колонок из экосистемы Сбер. Проект помогает не забывать принимать лекарства, отслеживать курс лечения, получать только справочную информацию о препаратах и искать лекарства в аптеках без медицинских рекомендаций.

## Что реализовано

- Добавление лекарства через API и голосовой сценарий
- Настройка расписания приёма
- Напоминания и повторные уведомления
- Подтверждение приёма и отложенное напоминание
- Учёт дней курса лечения
- Справка о препарате в безопасной формулировке
- Поиск аптек и сравнение цен на mock-данных
- Режим для пожилых пользователей
- Заготовка для уведомления родственников при пропуске
- Webhook под SmartApp API Сбера
- Экранные карточки и подсказки для устройств с экраном
- SSML-аудиосигналы для колонок и экранных устройств
- Help/exit-сценарии для прохождения модерации

## Ограничения модерации

- Навык не ставит диагнозы
- Навык не назначает лечение
- Все ответы о препаратах выдаются только в справочной форме
- В ответах используется дисклеймер: `Информация носит справочный характер и не заменяет консультацию врача`

Подробности по архитектуре и безопасным ограничениям: [docs/architecture.md](docs/architecture.md)

Подготовка к модерации SberApps, поля для Studio и сценарии для модератора:
[docs/sberapps_moderation.md](docs/sberapps_moderation.md)

Отчёт по последнему тестированию: [docs/test_report_2026-05-05.md](docs/test_report_2026-05-05.md)

## Стек

- Python 3.12
- FastAPI
- JSON-хранилище для MVP

## Структура

```text
app/
  main.py
  nlu.py
  safety.py
  schemas.py
  storage.py
  services/
data/
  drug_reference.json
  pharmacies.json
docs/
  architecture.md
tests/
  test_api.py
```

## Запуск

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Документация API будет доступна по адресу `http://127.0.0.1:8000/docs`.

## Статичный фронтенд для хостинга

В папке `frontend/` лежит статичный экран GrannyCare для поля `Хостинг фронтенда` в Studio Сбера:

- ближайший приём лекарства и таймер ответа
- крупные кнопки подтверждения и отложенного напоминания
- расписание препаратов
- mock-цены в аптеках
- безопасная справка с медицинским дисклеймером

Архив для загрузки можно собрать так:

```powershell
Compress-Archive -Path frontend\* -DestinationPath grannycare-frontend.zip -Force
```

Для сценария SmartApp API всё равно нужна внешняя HTTPS-ссылка на backend:
`/api/v1/sber/webhook`.

Перед загрузкой фронтенда в Studio пересоберите архив:

```powershell
Compress-Archive -Path frontend\* -DestinationPath grannycare-frontend.zip -Force
```

## Основные endpoints

- `POST /api/v1/skill/handle` — эмуляция голосового навыка
- `POST /api/v1/sber/webhook` — webhook в формате SmartApp API Сбера
- `POST /api/v1/medications` — добавить лекарство напрямую
- `GET /api/v1/medications/{user_id}` — список лекарств
- `POST /api/v1/intake/confirm` — подтвердить приём
- `POST /api/v1/intake/snooze` — отложить напоминание
- `GET /api/v1/course-status` — узнать день курса
- `GET /api/v1/drug-info` — справка по препарату
- `GET /api/v1/pharmacies/search` — поиск аптек и цен
- `GET /api/v1/notifications/{user_id}` — список уведомлений
- `PATCH /api/v1/users/{user_id}/settings` — режим для пожилых и настройки повторов
- `POST /api/v1/dev/scan-reminders` — ручной запуск планировщика для демо и тестов

## Пример диалога

1. Пользователь: `Добавь лекарство`
2. Ассистент: `Как называется препарат?`
3. Пользователь: `Аспирин`
4. Ассистент: `Когда принимать? Например: каждый день в 9 утра.`
5. Пользователь: `Каждый день в 9 утра`
6. Ассистент: `Сколько дней курс? Если курс не задан, скажите: без курса.`
7. Пользователь: `7 дней`
8. Ассистент: `Готово: аспирин добавлен в расписание. Напоминание каждый день в 09:00. Курс: 7 дней.`

## Пример запросов

Добавить лекарство через голосовой endpoint:

```bash
curl -X POST http://127.0.0.1:8000/api/v1/skill/handle ^
  -H "Content-Type: application/json" ^
  -d "{\"user_id\":\"demo-user\",\"utterance\":\"Напомни принимать аспирин каждый день в 9 утра\"}"
```

Получить справку по препарату:

```bash
curl "http://127.0.0.1:8000/api/v1/drug-info?name=парацетамол"
```

Запустить проверку напоминаний:

```bash
curl -X POST "http://127.0.0.1:8000/api/v1/dev/scan-reminders"
```

Пример запуска SmartApp webhook:

```bash
curl -X POST http://127.0.0.1:8000/api/v1/sber/webhook ^
  -H "Content-Type: application/json" ^
  -d "{\"sessionId\":\"demo-session\",\"messageId\":1,\"messageName\":\"RUN_APP\",\"uuid\":{\"userChannel\":\"B2C\",\"sub\":\"demo-user\",\"userId\":\"demo-user\"},\"payload\":{\"new_session\":true,\"meta\":{\"features\":{\"screen\":{\"enabled\":true}}},\"device\":{\"surface\":\"SBERBOX\",\"capabilities\":{\"screen\":{\"available\":true},\"speak\":{\"available\":true}}}}}"
```

## Что сделано для модерации Сбера

- Добавлен отдельный webhook под SmartApp API: [app/services/smartapp.py](app/services/smartapp.py)
- Для устройств с экраном ответы дублируются в `bubble` и `list_card`
- Для голосового интерфейса используется `pronounceTextType=application/ssml` и аудиосигналы через тег `audio`
- Для пошаговых сценариев включается `auto_listening`
- Для медицинских запросов встроен безопасный отказ и обязательный дисклеймер
- Добавлены сценарии `Помощь` и `Выход`

## Тесты

```bash
pytest -q
```

Покрыты end-to-end и moderation-readiness тесты SmartApp webhook:

- запуск `RUN_APP`
- пошаговое добавление лекарства
- поиск аптек и безопасный отказ
- сценарий без экрана
- подтверждение приёма после напоминания
- обработка `SERVER_ACTION` от фронтенда
- отсутствие `null` и переносов строк в ответах SmartApp API
- отсутствие тупиков в help/unknown/prompt-сценариях
- отсутствие защищенных брендов в видимых demo-данных
- завершение навыка

## Перед отправкой на модерацию

1. Разверните backend по HTTPS с TLS 1.2+.
2. В Studio укажите webhook: `https://<ваш-домен>/api/v1/sber/webhook`.
3. Загрузите `grannycare-frontend.zip` в поле хостинга frontend.
4. Заполните инструкцию для тестирования из [docs/sberapps_moderation.md](docs/sberapps_moderation.md).
5. Подготовьте политику конфиденциальности, потому что проект хранит расписание лекарств и может хранить контакт родственника.
