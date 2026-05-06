# Test Report

Дата проверки: 5 мая 2026.

## Окружение

- Рабочая папка: `c:\SBER_MISIS`
- Backend: FastAPI
- Python-зависимости: `requirements.txt`
- Тестовый запуск без scheduler, с временным `runtime_state.json` в `tmp_path`

## Автотесты

Команда:

```powershell
pytest -q
```

Результат:

```text
13 passed
```

Покрытые группы:

- REST API для добавления лекарств, напоминаний, справки и безопасного отказа.
- SmartApp API e2e: `RUN_APP`, `MESSAGE_TO_SKILL`, сценарий без экрана, выход.
- Пошаговое добавление лекарства через webhook.
- Подтверждение приема после напоминания.
- Поиск аптек и безопасный отказ.
- `SERVER_ACTION` от frontend к backend.
- Контракт ответов для модерации: без `null`, без переносов строк, с корректным `messageId`.
- Проверка, что видимые demo-данные не используют защищенные бренды Сбера/Салюта.
- Проверка, что help/unknown/prompt-сценарии не являются тупиками.

## Компиляция Python

Команда:

```powershell
python -m compileall -q app tests
```

Результат: ошибок синтаксиса нет.

## Live HTTP Smoke

Запускался настоящий локальный Uvicorn на случайном порту, после проверки процесс остановлен.

Проверены:

- `GET /health`
- `POST /api/v1/sber/webhook` с `RUN_APP`

Результат:

```text
health: ok
messageName: ANSWER_TO_USER
pronounceTextType: application/ssml
auto_listening: True
finished: False
suggestions: 3
```

## Frontend Archive

Архив пересобран командой:

```powershell
Compress-Archive -Path frontend\* -DestinationPath grannycare-frontend.zip -Force
```

Состав архива:

```text
app.js
index.html
styles.css
```

Размер архива на момент проверки: `4235` байт.

## Изменения для модерации

- Реплики ассистента приведены к нейтральной форме: убраны `Добавила`, `не нашел`, `не нашла`.
- Видимое название mock-аптеки `СберАптека на Тверской` заменено на нейтральное `Здоровье рядом на Тверской`.
- Кнопка `Проверить настройки` на frontend теперь дает статус, а не выглядит мертвой.
- Добавлена подробная инструкция подготовки к SberApps: [sberapps_moderation.md](sberapps_moderation.md).
- Добавлен шаблон политики конфиденциальности: [privacy_policy_template.md](privacy_policy_template.md).

## Остаточные риски перед реальной публикацией

- Нужен публичный HTTPS-deploy backend с TLS 1.2+.
- Нужна заполненная политика конфиденциальности с реальными реквизитами владельца.
- Если приложение публикуется не как демо, локальный каталог аптек нужно заменить реальным источником данных или убрать ценовые утверждения.
- Нужно подготовить и загрузить иконки/превью в размерах, указанных в [sberapps_moderation.md](sberapps_moderation.md).
- Для production-хранения реальных пользователей лучше заменить JSON-файл на БД с контролем доступа и резервным копированием.
