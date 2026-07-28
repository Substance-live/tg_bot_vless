"""Ручной smoke-тест node-агента через NodeClient.

Проверяет полный цикл против РЕАЛЬНОГО узла и подчищает за собой.

Запуск:
    python scripts/smoke_node.py http://127.0.0.1:8080 AGENT_SECRET
или через переменные окружения:
    NODE_URL=http://127.0.0.1:8080 NODE_SECRET=... python scripts/smoke_node.py
"""

from __future__ import annotations

import asyncio
import os
import sys
import uuid
from types import SimpleNamespace

from services.node_client import NodeClient


async def main() -> int:
    url = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("NODE_URL", "")
    secret = sys.argv[2] if len(sys.argv) > 2 else os.environ.get("NODE_SECRET", "")
    if not url or not secret:
        print("usage: python scripts/smoke_node.py <agent_url> <agent_secret>")
        return 2

    node = SimpleNamespace(name="smoke", country="XX", agent_url=url, agent_secret=secret)
    ext = f"smoke-{uuid.uuid4().hex[:8]}"

    async with NodeClient(node) as c:
        print("health:", await c.health_check())
        created = await c.create_vless_user(ext, expire_days=0, remark="smoke")
        print("create:", created.get("config_link"))
        got = await c.get_vless_user(ext)
        assert got and got["config_link"] == created["config_link"], "link mismatch"
        print("get: OK, is_enabled =", got.get("is_enabled"))
        # идемпотентность: повторный create → 409 → existing
        again = await c.create_vless_user(ext, expire_days=0)
        assert again["config_link"] == created["config_link"], "idempotency mismatch"
        print("idempotent create (409->existing): OK")
        print("mtproto:", (await c.get_mtproto_info()).get("tg_link"))
        await c.set_vless_enabled(ext, False)
        print("disabled:", (await c.get_vless_user(ext)).get("is_enabled"))
        await c.set_vless_enabled(ext, True)
        print("enabled:", (await c.get_vless_user(ext)).get("is_enabled"))
        await c.delete_vless_user(ext)
        assert await c.get_vless_user(ext) is None, "delete failed"
        print("delete: OK")

    print("\nSMOKE OK — узел отвечает по контракту.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
