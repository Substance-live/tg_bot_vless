#!/usr/bin/env bash
# Ждём БД, применяем миграции, запускаем оркестратор (API + бот-polling).
set -euo pipefail

echo "[entrypoint] waiting for database..."
python - <<'PY'
import asyncio, os, sys
import asyncpg

url = os.environ["DATABASE_URL"].replace("postgresql+asyncpg://", "postgresql://", 1)

async def wait():
    for attempt in range(30):
        try:
            conn = await asyncpg.connect(url)
            await conn.close()
            print(f"[entrypoint] db is up (attempt {attempt + 1})")
            return
        except Exception as exc:  # noqa: BLE001
            print(f"[entrypoint] db not ready ({exc}); retry in 2s")
            await asyncio.sleep(2)
    print("[entrypoint] db never came up", file=sys.stderr)
    sys.exit(1)

asyncio.run(wait())
PY

echo "[entrypoint] running migrations..."
alembic upgrade head

echo "[entrypoint] starting orchestrator..."
exec uvicorn main:app --host "${API_HOST:-0.0.0.0}" --port "${API_PORT:-8000}"
