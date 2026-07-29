"""Async HTTP-клиент к vpn-node-agent (контракт 03 §7).

Один клиент на узел: берёт agent_url и agent_secret из ORM-строки Node.
Базовый путь = f"{node.agent_url}/api/v1". Заголовок X-Agent-Secret на всех
вызовах кроме health. 409 (клиент уже есть) трактуется как успех через поле
existing; 404 → None. Ретраи только на транспортные ошибки и 502/503.
"""

from __future__ import annotations

import asyncio
from typing import Any

import httpx

from core.config import settings
from core.logging import get_logger
from db.models import Node

logger = get_logger("node_client")


class NodeClientError(Exception):
    """Базовая ошибка взаимодействия с node-агентом."""


class NodeUnavailableError(NodeClientError):
    """Агент/бэкенд недоступен (502, таймаут, connection refused)."""


class NodeForbiddenError(NodeClientError):
    """Неверный или отсутствующий X-Agent-Secret (403)."""


class NodeValidationError(NodeClientError):
    """Невалидные данные запроса (422)."""


class NodeInternalError(NodeClientError):
    """Непредвиденная ошибка агента (500)."""


_RETRY_STATUSES = {502, 503}


class NodeClient:
    """Клиент к одному узлу. Использовать как async context manager."""

    def __init__(
        self,
        node: Node,
        *,
        timeout: int | None = None,
        retries: int | None = None,
    ) -> None:
        self._node = node
        self._base_url = f"{node.agent_url.rstrip('/')}/api/v1"
        self._secret = node.agent_secret
        self._timeout = timeout if timeout is not None else settings.NODE_AGENT_TIMEOUT_SECONDS
        self._retries = retries if retries is not None else settings.NODE_AGENT_RETRY_COUNT
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> NodeClient:
        # verify: путь к PEM с доверенными сертами агентов (пиннинг self-signed
        # для https-узлов) либо True (системные CA). Для http-узлов не влияет.
        verify: str | bool = settings.NODE_AGENT_CA_BUNDLE or True
        self._client = httpx.AsyncClient(timeout=self._timeout, verify=verify)
        return self

    async def __aexit__(self, *exc: object) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    # ── Внутренний транспорт ────────────────────────────────────────────

    async def _request(
        self,
        method: str,
        path: str,
        *,
        auth: bool = True,
        json: dict | None = None,
        ok_codes: tuple[int, ...] = (200,),
    ) -> httpx.Response:
        assert self._client is not None, "NodeClient must be used as async context manager"
        url = f"{self._base_url}{path}"
        headers = {"X-Agent-Secret": self._secret} if auth else {}

        last_exc: Exception | None = None
        for attempt in range(self._retries + 1):
            try:
                resp = await self._client.request(method, url, json=json, headers=headers)
            except httpx.TransportError as exc:
                last_exc = exc
                if attempt < self._retries:
                    await asyncio.sleep(min(0.5 * 2**attempt, 5.0))
                    continue
                logger.warning("node.transport_error", node=self._node.name, error=str(exc))
                raise NodeUnavailableError(f"transport error: {exc}") from exc

            if resp.status_code in _RETRY_STATUSES and attempt < self._retries:
                await asyncio.sleep(min(0.5 * 2**attempt, 5.0))
                continue
            return resp

        # Недостижимо: цикл либо вернул resp, либо кинул исключение.
        raise NodeUnavailableError(str(last_exc))

    @staticmethod
    def _slug(resp: httpx.Response) -> str:
        try:
            return str(resp.json().get("error", ""))
        except Exception:
            return ""

    def _raise_for_status(self, resp: httpx.Response) -> None:
        code = resp.status_code
        if code == 403:
            raise NodeForbiddenError(self._slug(resp) or "forbidden")
        if code == 422:
            raise NodeValidationError(self._slug(resp) or "validation_error")
        if code in _RETRY_STATUSES:
            raise NodeUnavailableError(self._slug(resp) or f"http {code}")
        if code >= 500:
            raise NodeInternalError(self._slug(resp) or f"http {code}")
        raise NodeClientError(f"unexpected http {code}: {resp.text[:200]}")

    # ── VLESS ───────────────────────────────────────────────────────────

    async def create_vless_user(
        self, external_id: str, expire_days: int, remark: str | None = None
    ) -> dict[str, Any]:
        """POST /vless/users. 409 → возвращает existing (идемпотентность)."""
        body: dict[str, Any] = {"external_id": external_id, "expire_days": expire_days}
        if remark is not None:
            body["remark"] = remark
        resp = await self._request("POST", "/vless/users", json=body)
        if resp.status_code == 201:
            return resp.json()
        if resp.status_code == 409:
            existing = resp.json().get("existing")
            if existing:
                return existing
            # Крайне маловероятно: 409 без existing — считаем успехом с пустыми данными.
            return {"external_id": external_id}
        self._raise_for_status(resp)

    async def get_vless_user(self, external_id: str) -> dict[str, Any] | None:
        """GET /vless/users/{id}. 404 → None."""
        resp = await self._request("GET", f"/vless/users/{external_id}")
        if resp.status_code == 200:
            return resp.json()
        if resp.status_code == 404:
            return None
        self._raise_for_status(resp)

    async def set_vless_expiry(self, external_id: str, expire_days: int) -> dict[str, Any] | None:
        return await self._patch_vless(external_id, {"expire_days": expire_days})

    async def set_vless_enabled(self, external_id: str, is_enabled: bool) -> dict[str, Any] | None:
        return await self._patch_vless(external_id, {"is_enabled": is_enabled})

    async def _patch_vless(self, external_id: str, body: dict[str, Any]) -> dict[str, Any] | None:
        resp = await self._request("PATCH", f"/vless/users/{external_id}", json=body)
        if resp.status_code == 200:
            return resp.json()
        if resp.status_code == 404:
            return None
        self._raise_for_status(resp)

    async def delete_vless_user(self, external_id: str) -> None:
        resp = await self._request(
            "DELETE", f"/vless/users/{external_id}", ok_codes=(204,)
        )
        if resp.status_code in (204, 404):
            return
        self._raise_for_status(resp)

    # ── MTProto ─────────────────────────────────────────────────────────

    async def get_mtproto_info(self) -> dict[str, Any]:
        """GET /mtproto/info. Одна общая ссылка на узел."""
        resp = await self._request("GET", "/mtproto/info")
        if resp.status_code == 200:
            return resp.json()
        self._raise_for_status(resp)

    # ── Health ──────────────────────────────────────────────────────────

    async def health_check(self) -> dict[str, Any]:
        """GET /health (без авторизации)."""
        resp = await self._request("GET", "/health", auth=False)
        if resp.status_code == 200:
            return resp.json()
        self._raise_for_status(resp)
