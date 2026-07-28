# vpn-orchestrator

Центральный сервис VPN-as-a-Service: Telegram-бот (aiogram 3) + Admin REST API (FastAPI),
бизнес-логика, оркестрация Node Agent'ов. Спецификации — в `tz/` (`02_ORCHESTRATOR_SPEC.md`),
план реализации MVP — `tz/06_ORCHESTRATOR_IMPL_PLAN.md`.

> Статус: **Этап 0 (каркас)**. Бот и API поднимаются в одном процессе; боевая логика — далее.

## Требования
- Python 3.11+

## Локальный запуск

```bash
python -m venv .venv
# Windows:
.venv\Scripts\activate
# Linux/macOS:
# source .venv/bin/activate

pip install -r requirements.txt

cp .env.example .env        # заполнить BOT_TOKEN (опционально на Этапе 0)

uvicorn main:app --reload --port 8000
```

- Swagger UI: http://localhost:8000/docs
- Health:     http://localhost:8000/api/v1/health

Если `BOT_TOKEN` пуст — бот не запускается, работает только API (в логах предупреждение).
С заданным `BOT_TOKEN` бот отвечает на `/start`.

## Структура

```
core/      # config (pydantic-settings), logging (structlog), security/messages (заглушки)
bot/       # aiogram: factory, handlers, keyboards, middlewares, filters
api/       # FastAPI: routers, schemas, dependencies
services/  # node_client, provisioning, key_manager, subscription (далее)
db/        # SQLAlchemy models + Alembic migrations (Этап 1)
scheduler/ # APScheduler-задачи (после MVP)
main.py    # точка входа: FastAPI + bot polling в одном процессе
```
