# Self-Hosted SMS Gateway

A professional, self-hosted SMS Gateway platform built with Django, Django REST
Framework, Django Channels and Celery.

The backend exposes a REST API to send/receive SMS through Android gateway
devices that connect over WebSocket, Webhooks to notify your application about
delivered and received messages, API key + JWT authentication, per-key rate
limiting, OTP delivery, usage metering and an audit log.

## Features

- Send single or bulk SMS through a REST API.
- Android devices connect over WebSocket and execute send jobs.
- Automatic SIM/device selection (`least_used` / round-robin / priority).
- Delivery reports (`sms.result`) with automatic retries and message expiry.
- Incoming SMS saved and forwarded to webhooks (HMAC-signed).
- API key authentication (`Authorization: Api-Key <sk-...>`) and JWT for users.
- Per-key throttle windows (per second / minute / hour / day / month).
- Webhook management with retries and a dead-letter queue.
- OTP send/verify flow, usage records/summaries, audit log and a dashboard API.
- Interactive API docs (Swagger + Redoc) via drf-spectacular.

## Tech Stack

| Layer | Technology |
|---|---|
| Web/API | Django 5.2, DRF, Django Channels (WebSocket) |
| Task queue | Celery + Redis (Celery Beat scheduler) |
| Real-time layer | Redis channel layer (`channels-redis`) |
| Cache / rate limiting | Redis (`django-redis`) |
| Database | PostgreSQL (or SQLite for local dev) |
| ASGI server | Daphne (cross-platform) / gunicorn+uvicorn on Linux |

## Architecture

```
                 ┌──────────────────────────────┐
                 │          redis                │
                 │  broker · cache · channels   │
                 └─────┬───────────┬────────────┘
                       │           │
          ┌────────────▼───┐   ┌────▼──────────────┐
          │  API (Daphne)  │   │  Celery worker    │
          │  REST + WS     │   │  + beat           │
          └───┬────────┬───┘   └──────▲────────────┘
              │        │             │
   Android ▶  ws/device │   webhooks │  message jobs
  gateway devices      │             │
                       ▼             │
              ┌──────────────────┐   │
              │  PostgreSQL      │   │
              └──────────────────┘   │
                                     │
```

Flow: The API enqueues a message → the Celery worker selects a device/SIM →
pushes the job to the connected Android device over its WebSocket group → the
device sends the SMS and reports back an `sms.result` → the worker updates the
message, records usage and fires webhooks. Received SMS come back over the same
WebSocket as `sms.received` and are stored + forwarded to webhooks.

## Quick Start (no Docker)

### 1. Requirements

- Python 3.12+
- Redis >= 7 (required for Celery + channels + cache)
- PostgreSQL (optional — SQLite works out of the box)

### 2. Setup

```bash
# create and activate a virtual environment
python -m venv venv
venv\Scripts\activate              # Windows
source venv/bin/activate           # Linux/macOS
```

```bash
pip install -r requirements.txt

# environment configuration
cp .env.example .env               # then edit .env

# database
python manage.py migrate

# admin / operator user
python manage.py createsuperuser
```

Convenience (non-interactive superuser):

```bash
set DJANGO_SUPERUSER_USERNAME=admin^
set DJANGO_SUPERUSER_PASSWORD=ChangeMe123!^
set DJANGO_SUPERUSER_EMAIL=admin@example.com
python manage.py createsuperuser --noinput
```

### 3. Run the services

```bash
# Redis must be running first
redis-server

# terminal 1 – API server (HTTP + WebSocket via Daphne)
python manage.py runserver 0.0.0.0:8000
# or: daphne -b 0.0.0.0 -p 8000 httpsms.asgi:application

# terminal 2 – Celery worker
celery -A httpsms worker -l info -P solo        # -P solo on Windows

# terminal 3 – scheduler (optional but recommended)
celery -A httpsms beat -l info
```

### 4. Tests

```bash
python manage.py test tests --settings=httpsms.test_settings
```

## API Reference

Interactive docs: `http://localhost:8000/api/docs/` (Swagger) and
`http://localhost:8000/api/redoc/` (Redoc). Schema: `/api/schema/`.

All endpoints live under `/api/v1/`.

### Authentication

- **User (JWT):** register → `POST /api/v1/auth/login/` (body:
  `{"email": "...", "password": "..."}`) → use
  `Authorization: Bearer <access>`. Refresh: `POST /auth/refresh/`, logout
  blacklists the token, `GET /auth/me/` returns the profile.
- **Machine (API Key):** create a key in the web/API then send
  `Authorization: Api-Key sk-...` (no bearer prefix). Keys are scoped to a
  customer and have their own per-key rate limits.

### Accounts

| Method | Path | Description |
|---|---|---|
| POST | `/api/v1/auth/register/` | Register a customer user |
| POST | `/api/v1/auth/login/` | JWT login (`{access, refresh}`) |
| POST | `/api/v1/auth/refresh/` | Rotate refresh token |
| POST | `/api/v1/auth/verify/` | Verify a JWT |
| POST | `/api/v1/auth/logout/` | Logout + blacklist token |
| GET  | `/api/v1/auth/me/` | Current user profile |
| POST | `/api/v1/auth/change-password/` | Change password |
| GET  | `/api/v1/auth/users/` | List users |
| POST | `/api/v1/auth/users/create/` | Create a customer user |

### API Keys

| Method | Path | Description |
|---|---|---|
| GET/POST | `/api/v1/api-keys/` | List / create API keys |
| GET/PUT/DELETE | `/api/v1/api-keys/{pk}/` | Key detail |
| POST | `/api/v1/api-keys/{pk}/revoke/` | Revoke a key |
| GET | `/api/v1/api-keys/{pk}/status/` | Key status |

The created key is returned only once (`sk_...`).

### Devices

| Method | Path | Description |
|---|---|---|
| GET/POST | `/api/v1/devices/` | List / register a device record |
| POST | `/api/v1/devices/pair/` | Issue pairing uuid + token for an Android device |
| GET/PUT/DELETE | `/api/v1/devices/{pk}/` | Device detail |
| GET/POST | `/api/v1/devices/{pk}/status/` | Device status / change status |
| GET/POST | `/api/v1/devices/sims/` | List / create SIM cards |

`POST /api/v1/devices/pair/` returns:

```json
{
  "success": true,
  "device": {
    "id": "...", "device_uuid": "...", "token": "...",
    "websocket_url": "/ws/device/"
  }
}
```

### Messages

| Method | Path | Description |
|---|---|---|
| GET/POST | `/api/v1/messages/` | List / send one SMS |
| POST | `/api/v1/messages/bulk/` | Bulk send (`recipients`: array) |
| GET | `/api/v1/messages/incoming/` | Received SMS |
| GET | `/api/v1/messages/incoming/{public_id}/` | Received SMS detail |
| GET | `/api/v1/messages/{public_id}/attempts/` | Delivery attempts |
| GET | `/api/v1/messages/{public_id}/` | Message detail |

Send a single SMS:

```bash
curl -X POST http://localhost:8000/api/v1/messages/ \
  -H "Authorization: Api-Key sk-xxxx" \
  -H "Content-Type: application/json" \
  -d '{
    "to": ["+201234567890"],
    "body": "OTP is 123456",
    "priority": "NORMAL",
    "expires_in_seconds": 300,
    "idempotency_key": "order-123"
  }'
```

Bulk send: same fields with a larger `recipients`/`to` list; the endpoint returns
a `bulk_group_id` and individual message ids.

### Webhooks (your app receives SMS + delivery events)

| Method | Path | Description |
|---|---|---|
| GET/POST | `/api/v1/webhooks/` | List / register webhook |
| GET/PUT/DELETE | `/api/v1/webhooks/{pk}/` | Webhook detail |
| GET | `/api/v1/webhooks/{pk}/deliveries/` | Delivery history |
| POST | `/api/v1/webhooks/{pk}/test/` | Fire a test event |

Webhook payload: `{"event": "message.received", "message": {...}}` signed with
`X-HttpSMS-Signature` = `HMAC-SHA256(WEBHOOK_SECRET, raw_body)`.

### OTP

| Method | Path | Description |
|---|---|---|
| POST | `/api/v1/otp/send/` | Send OTP via SMS (`to`, optional `channel`) |
| POST | `/api/v1/otp/verify/` | Verify code (`otp_id`, `code`) |

### Usage

| Method | Path | Description |
|---|---|---|
| GET | `/api/v1/usage/` | Usage records (date/event filters) |
| GET | `/api/v1/usage/summary/` | Daily/monthly summaries |
| GET | `/api/v1/usage/totals/` | Aggregated totals by device/SIM |
| GET | `/api/v1/usage/timeline/` | Admin timeline across customers |

### Audit

| Method | Path | Description |
|---|---|---|
| GET | `/api/v1/audit/` | Audit log entries |

### Dashboard

| Method | Path | Description |
|---|---|---|
| GET | `/api/v1/dashboard/stats/` | Customer statistics |
| GET | `/api/v1/dashboard/recent/` | Recent messages |
| GET | `/api/v1/dashboard/status-breakdown/` | Status counts |

## Android Device Protocol (WebSocket)

The gateway device connects to `wss://host/ws/device/?device_uuid=<uuid>&token=<token>`
in the query string. Invalid credentials close with code `4001`.

Server → device on connect:

```json
{
  "type": "device.state",
  "status": "connected",
  "device_uuid": "...",
  "pending_sims": [{"slot": 0, "phone_number": "...", "carrier": "..."}]
}
```

### Device → server messages

| `type` | Payload | Notes |
|---|---|---|
| `heartbeat` | — | Server replies `{"type":"heartbeat","ack":true,"count":N}` |
| `device.register` | `{"data":{"sims":[{slot, phone_number, carrier, country}]}}` | Report SIMs |
| `sms.result` | `{"data":{message_id, success, error?, sim_slot?}}` | Delivery report → `sms.result.ack` |
| `sms.received` | `{"data":{from, to, body, message_id?}}` | Incoming SMS → `sms.received.ack` |
| `ack` | — | Touch `last_seen` |

### Server → device (send job)

```json
{
  "type": "sms.send",
  "message": {
    "message_id": "...", "sim_slot": 1,
    "to": "+201234567890", "body": "hello"
  }
}
```

The device must send an `sms.result` back with the same `message_id` and
`sim_slot`, e.g. `{"type":"sms.result","data":{"message_id":"...","success":true,"sim_slot":1}}`.

A device can be marked online/offline in the UI; offline devices still receive
queued jobs once they reconnect, and `requeue-stale-sending-messages` runs every
minute to recover stuck messages.

## Configuration (`env` variables)

See [.env.example](.env.example): `SECRET_KEY`, `DEBUG`, `ALLOWED_HOSTS`,
`DATABASE_URL`, `REDIS_URL`, JWT lifetimes, webhook settings, rate-limit windows
and OTP settings.

## Production Notes

- Set `DEBUG=False`, a strong `SECRET_KEY`, `ALLOWED_HOSTS`, and
  `SECURE_SSL_REDIRECT=True` behind TLS. With `SECRET_KEY` still at the insecure
  default, the app refuses to boot in production (`ImproperlyConfigured`).
- Use PostgreSQL via `DATABASE_URL=postgres://user:pass@host:5432/db`.
- Run `python manage.py collectstatic --noinput` and serve the ASGI app with
  Daphne, or on Linux with gunicorn + uvicorn workers if preferred.
- Deploy Redis + Celery worker + Celery beat as separate processes.
- This project is intentionally Docker-free. A complete **VPS/Ubuntu deployment
  kit (systemd units + nginx + step-by-step guide)** lives in [deploy/](deploy/)
  — see [deploy/DEPLOY.md](deploy/DEPLOY.md).
- Set `TRUSTED_PROXY=True` when behind nginx/Caddy so Django trusts
  `X-Forwarded-Proto` for the HTTPS redirect.

## Project Structure

```
httpsms/        settings, ASGI/WSGI, root urls, package setup
core/           shared mixins, permissions, exceptions, utils
accounts/       users, JWT auth, profile, password
customers/      tenants / customers, quotas, limits
api_keys/        machine API keys + auth principals
devices/        devices, SIMs, pairing, WebSocket consumer
messaging/      message models, sender services, tasks, views
webhooks/       webhook config, deliveries, HMAC signing
usage/          usage records, summaries, daily report task
otp/            OTP send/verify flow
notifications/  notification models/triggers
audit/          audit log models + middleware
dashboard/      aggregate stats endpoints
deploy/         VPS deployment: systemd units, nginx, DEPLOY.md guide
tests/          full test suite
```#   h t t p s - s m s  
 