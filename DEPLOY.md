# Деплой vpn-orchestrator (MVP)

Оркестратор (Telegram-бот + FastAPI) запускается в docker-compose вместе с
Postgres на **одном из VPS**. Узлы (`vpn-node-agent`) уже развёрнуты; связь с
ними — по **HTTP на порт 8080** (без TLS/nginx).

## Предпосылки

- Docker + docker compose на VPS.
- На каждом узле работает `vpn-node-agent` (порт 8080).
- Firewall (ufw) на узлах пускает 8080 **только с IP оркестратора**:
  - локальный узел (агент на том же хосте): нужен доступ из docker-сети
    оркестратора к хосту — разрешить подсеть docker-бриджа, например
    `sudo ufw allow from 172.16.0.0/12 to any port 8080 proto tcp`;
  - удалённый узел: `sudo ufw allow from <ORCHESTRATOR_PUBLIC_IP> to any port 8080 proto tcp`.

## Шаги

1. Скопировать репозиторий на VPS, перейти в каталог.
2. `cp .env.example .env` и заполнить:
   - `BOT_TOKEN` — токен от @BotFather;
   - `ADMIN_TELEGRAM_IDS` — ваш Telegram ID (узнать у @userinfobot);
   - `NODES` — JSON двух узлов. Локальный узел через `host.docker.internal`,
     удалённый — по публичному IP. Секреты `agent_secret` = `AGENT_SECRET`
     из `.env` соответствующего node-агента:
     ```
     NODES=[{"name":"Node-DE","country":"DE","agent_url":"http://host.docker.internal:8080","agent_secret":"SECRET_DE"},{"name":"Node-NL","country":"NL","agent_url":"http://5.6.7.8:8080","agent_secret":"SECRET_NL"}]
     ```
   - `POSTGRES_*` при желании сменить пароль (тогда синхронно поправить `DATABASE_URL`).
3. (Опционально, до запуска) проверить доступность узлов:
   ```
   python scripts/smoke_node.py http://<ip>:8080 <AGENT_SECRET>
   ```
4. Поднять стек:
   ```
   docker compose up -d --build
   ```
   Entrypoint дождётся БД, накатит миграции (`alembic upgrade head`) и запустит
   оркестратор. Узлы засеются из `NODES` при старте.
5. Логи: `docker compose logs -f orchestrator`.

## Проверка MVP-сценария

1. Админ в боте: `/newuser Alice` → получить одноразовый ключ.
2. С другого аккаунта: `/activate <key>` → приходят VLESS по всем узлам + MTProto.
3. `/configs`, `/status` — данные читаются живьём (отключение клиента в 3x-ui
   сразу видно).
4. Админ: `/disable Alice` → VLESS перестаёт работать; `/enable Alice` → снова работает.

## Обновление

```
git pull && docker compose up -d --build
```
Миграции применяются автоматически при старте контейнера.
