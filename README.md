# Chatterbox

Chatterbox is a production-minded realtime chat application being built incrementally as a modular monolith. This repository contains the **observability and hardening release**: horizontally scalable FastAPI instances backed by PostgreSQL and Redis, private MinIO object storage, secure token-based authentication, direct conversations, persisted message history and receipts, distributed presence and typing signals, reconnect recovery, a responsive React chat workspace, operational telemetry, health probes, optional malware scanning, migrations, tests, containers, and CI.

Each FastAPI instance owns only its local WebSocket connections. Redis Pub/Sub routes user-targeted events across instances, while expiring Redis leases coordinate global presence and typing state. PostgreSQL remains the source of truth for users, conversations, messages, attachment metadata, receipts, unread counts, and `last_seen`. MinIO stores private attachment objects; browsers upload directly through short-lived presigned URLs, while downloads are authorized and streamed by the API.

## Foundation features

- Register with a normalized, unique username and email
- Sign in with either username or email
- Argon2 password hashing
- JWT access tokens with configurable expiry
- Persisted refresh tokens, one-time rotation, revocation, and logout
- Bearer-protected `GET /auth/me` route
- Authenticated user search without exposing email addresses
- Idempotent direct-conversation creation using a canonical participant key
- Membership-protected conversation and message access
- PostgreSQL message persistence and deterministic cursor pagination
- Conversation lists with latest-message summaries
- Per-conversation unread counts and read-through acknowledgements
- Authenticated `WS /ws` connections using the WebSocket subprotocol header
- Typed message, receipt, presence, typing, connection, and error events
- Member-targeted delivery after successful database commit
- First/last-socket presence transitions with durable `last_seen` timestamps
- Automatic delivery acknowledgement when an online recipient receives a message
- Expiring typing indicators that cannot remain stuck indefinitely
- Redis Pub/Sub delivery across multiple FastAPI instances
- Crash-tolerant presence leases and globally coordinated typing expiry
- Redis-backed rate limits shared by every backend instance
- Automatic reconnect with exponential backoff up to 30 seconds
- Post-cursor REST recovery for messages missed while disconnected
- Private message attachments for images, PDF, ZIP, and text files
- Short-lived presigned MinIO uploads with size and media-type verification
- Transactional, single-use attachment binding to messages
- Membership-authorized attachment downloads streamed through the API
- Distributed cleanup of abandoned uploads using a Redis lock
- Optional fail-closed ClamAV scanning before an upload can be attached
- ETag-guarded promotion from mutable upload keys to immutable delivery keys
- JSON request logs with validated correlation IDs and trace correlation
- Prometheus HTTP, WebSocket, and attachment-scan metrics with alert rules
- Optional OTLP/HTTP tracing for FastAPI and SQLAlchemy
- Separate liveness and dependency-aware readiness probes
- Gateway security headers and documented backup, restore, and rotation runbooks
- Consistent API error envelopes without sensitive fields
- Async SQLAlchemy 2 data access and Alembic migrations
- Responsive React + TypeScript authentication and chat workspace
- TanStack Query for server state and focused Zustand session/chat stores
- PostgreSQL, Redis, MinIO, backend, and frontend in Docker Compose
- Backend integration tests and frontend component tests
- GitHub Actions lint, test, type-check, and build validation

## Architecture

```mermaid
flowchart LR
    Browser[React + Ant Design] <-->|REST + WebSockets| Gateway[Nginx gateway]
    Gateway --> API1[FastAPI instance 1]
    Gateway --> API2[FastAPI instance 2]
    API1 <-->|Pub/Sub + leases| Redis[(Redis)]
    API2 <-->|Pub/Sub + leases| Redis
    API1 --> DB[(PostgreSQL)]
    API2 --> DB
    Prometheus[Prometheus] -->|Scrape metrics| API1
    Prometheus -->|Scrape metrics| API2
    API1 -.->|Optional OTLP traces| Collector[OTel collector]
    API2 -.->|Optional OTLP traces| Collector
    Browser -->|Presigned PUT| MinIO[(Private MinIO bucket)]
    API1 -->|Validate + stream| MinIO
    API2 -->|Validate + stream| MinIO
    API1 -.->|Optional scan| ClamAV[ClamAV]
    API2 -.->|Optional scan| ClamAV
```

The backend is a layered modular monolith. Routes handle HTTP concerns, services own business transactions, repositories contain database queries, schemas define external contracts, and SQLAlchemy models define persistence. Redis contains only recoverable coordination state; a Redis outage never changes the durable message model. The MinIO bucket has no anonymous read policy, so every download still passes through conversation authorization.

## Technology stack

| Area | Technology |
| --- | --- |
| API | Python, FastAPI, Pydantic |
| Persistence | PostgreSQL, async SQLAlchemy, Alembic |
| Authentication | Argon2 via pwdlib, signed JWTs, persisted refresh-token JTIs |
| Web | React, strict TypeScript, Vite, Ant Design |
| Client state | TanStack Query, Zustand |
| Infrastructure | Docker Compose, Redis, MinIO, Nginx, Prometheus, optional ClamAV |
| Observability | JSON logs, Prometheus metrics/alerts, OpenTelemetry OTLP tracing |
| Quality | Pytest, Ruff, Vitest, Testing Library, ESLint, GitHub Actions |

## Quick start with Docker

Requirements: Docker with Compose v2.

```bash
cp .env.example .env
```

Replace `JWT_SECRET` and the development passwords in `.env`, then run:

```bash
docker compose up --build
```

To run two backend replicas behind the included gateway:

```bash
docker compose up --build --scale backend=2
```

Open:

- Web app: <http://localhost:3000>
- API documentation: <http://localhost:8000/docs>
- API health check: <http://localhost:8000/health>
- MinIO console: <http://localhost:9001>
- Prometheus: <http://localhost:9090>

The one-shot migration service waits for PostgreSQL and applies `alembic upgrade head` before any API replicas start. Stop the stack with `docker compose down`. Volumes are retained; `docker compose down -v` also removes local development data.

## Local development

The backend supports Python 3.9+, while its container and CI use Python 3.12.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e './backend[dev]'
docker compose up -d postgres
cd backend
DATABASE_URL=postgresql+asyncpg://chat:chat_dev_password@localhost:5432/chat alembic upgrade head
DATABASE_URL=postgresql+asyncpg://chat:chat_dev_password@localhost:5432/chat uvicorn app.main:app --reload
```

In another terminal:

```bash
cd frontend
npm install
npm run dev
```

The Vite app runs at <http://localhost:5173> and calls `http://localhost:8000` by default.

## Environment variables

| Variable | Purpose | Development default |
| --- | --- | --- |
| `DATABASE_URL` | Async SQLAlchemy PostgreSQL connection | Compose PostgreSQL service |
| `JWT_SECRET` | HMAC signing key; use at least 32 random characters | Insecure development value |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Access-token lifetime | `15` |
| `REFRESH_TOKEN_EXPIRE_DAYS` | Refresh-token lifetime | `7` |
| `CORS_ORIGINS` | JSON array of allowed browser origins | Ports `3000` and `5173` |
| `REDIS_URL` | Pub/Sub, presence, typing, and rate-limit store | `redis://redis:6379/0` |
| `REDIS_REQUIRED` | Fail startup when Redis is unavailable | `true` in Compose |
| `REDIS_KEY_PREFIX` | Namespace for shared Redis keys | `chatterbox` |
| `PRESENCE_TTL_SECONDS` | Lifetime of an instance's presence lease | `30` |
| `PRESENCE_HEARTBEAT_SECONDS` | Presence lease refresh interval | `10` |
| `TYPING_TTL_SECONDS` | Maximum lifetime of a typing state | `5` |
| `REALTIME_RATE_LIMIT_WINDOW_SECONDS` | Shared realtime rate-limit window | `60` |
| `MESSAGE_SEND_RATE_LIMIT` | Messages allowed per user/window | `30` |
| `TYPING_RATE_LIMIT` | Typing updates allowed per user/window | `120` |
| `RECEIPT_RATE_LIMIT` | Read updates allowed per user/window | `120` |
| `MINIO_ROOT_USER` | Local object-storage administrator | `minioadmin` |
| `MINIO_ROOT_PASSWORD` | Local object-storage password | Development-only value |
| `MINIO_CORS_ALLOWED_ORIGINS` | Comma-separated browser origins allowed to upload | Ports `3000` and `5173` |
| `MINIO_ENDPOINT` | Backend-visible MinIO host and port | `minio:9000` in Compose |
| `MINIO_PUBLIC_ENDPOINT` | Browser-visible host and port used in presigned URLs | `localhost:9000` |
| `MINIO_ACCESS_KEY` / `MINIO_SECRET_KEY` | Credentials used to sign and access attachment objects | Local administrator credentials |
| `MINIO_BUCKET` | Private attachment bucket | `chat-attachments` |
| `MINIO_REGION` | S3 signing region | `us-east-1` |
| `MINIO_SECURE` / `MINIO_PUBLIC_SECURE` | Enable HTTPS for internal/public endpoints | `false` |
| `MINIO_REQUIRED` | Fail startup when attachment storage is unavailable | `true` in Compose |
| `ATTACHMENT_MAX_BYTES` | Maximum object size accepted by the API | `10485760` (10 MiB) |
| `ATTACHMENT_MAX_PER_MESSAGE` | Maximum attachments bound to one message | `5` |
| `ATTACHMENT_UPLOAD_EXPIRE_MINUTES` | Presigned upload URL lifetime | `15` |
| `ATTACHMENT_PENDING_TTL_HOURS` | Age after which an unbound upload is abandoned | `24` |
| `ATTACHMENT_CLEANUP_INTERVAL_SECONDS` | Distributed cleanup interval | `3600` |
| `ATTACHMENT_SCAN_MODE` | Attachment scanner: `disabled` or `clamav` | `disabled` |
| `CLAMAV_HOST` / `CLAMAV_PORT` | ClamAV daemon endpoint | `clamav:3310` in Compose |
| `CLAMAV_TIMEOUT_SECONDS` | Per-file scan timeout | `15` |
| `LOG_LEVEL` | Structured backend log level | `INFO` |
| `OTEL_SERVICE_NAME` | OpenTelemetry service identity | `chatterbox-api` |
| `OTEL_EXPORTER_OTLP_TRACES_ENDPOINT` | Optional OTLP/HTTP traces endpoint | Empty (disabled) |
| `OTEL_EXPORT_TIMEOUT_SECONDS` | Trace export timeout | `5` |
| `HEALTH_CHECK_TIMEOUT_SECONDS` | Per-dependency readiness timeout | `2` |
| `VITE_API_URL` | Browser-visible API base URL | `http://localhost:8000` |

Never use the example credentials in a deployed environment. For a public deployment, refresh tokens should move from browser session storage to Secure, HttpOnly, SameSite cookies with CSRF protection.

## API

All request and response bodies use JSON. Interactive OpenAPI documentation is generated at `/docs`.

| Method | Route | Authentication | Purpose |
| --- | --- | --- | --- |
| `POST` | `/auth/register` | Public | Create a user and token pair |
| `POST` | `/auth/login` | Public | Authenticate by username or email |
| `POST` | `/auth/refresh` | Refresh token in body | Rotate and return a new token pair |
| `POST` | `/auth/logout` | Refresh token in body | Revoke the refresh token |
| `GET` | `/auth/me` | Bearer access token | Return the current user |
| `GET` | `/users?q=` | Bearer access token | Search other users |
| `GET` | `/users/{id}` | Bearer access token | Get a public user profile |
| `POST` | `/conversations` | Bearer access token | Start or retrieve a direct conversation |
| `GET` | `/conversations` | Bearer access token | List the current user's conversations |
| `GET` | `/conversations/{id}` | Bearer access token | Get an authorized conversation |
| `GET` | `/conversations/{id}/messages` | Bearer access token | Read history with `before` or recover with `after` |
| `POST` | `/conversations/{id}/messages` | Bearer access token | Persist a message |
| `POST` | `/conversations/{id}/attachments` | Bearer access token + membership | Reserve metadata and receive a presigned PUT URL |
| `POST` | `/attachments/{id}/complete` | Bearer access token + uploader | Verify and finalize an uploaded object |
| `GET` | `/attachments/{id}/download` | Bearer access token + membership | Stream an attachment from private storage |

Errors have one stable envelope:

```json
{
  "error": {
    "code": "INVALID_CREDENTIALS",
    "message": "Invalid login or password"
  }
}
```

### Attachment flow

1. Reserve an attachment with its sanitized filename, media type, and exact byte size.
2. Upload the object directly to the returned presigned MinIO URL using the returned headers.
3. Complete the reservation so the API verifies the object's size and media type,
   runs the configured malware scanner, and conditionally promotes that exact ETag
   to a separate delivery key.
4. Include the finalized attachment UUID in a REST or WebSocket message request.

Finalized attachments can be bound once, only by their uploader, and only to the conversation for which they were reserved. Binding the attachment and creating the message happen in one PostgreSQL transaction. Unbound reservations are removed from MinIO and PostgreSQL after their configured TTL.

Scanning is disabled for local development. To run the included ClamAV daemon and
fail closed when it is unavailable:

```bash
ATTACHMENT_SCAN_MODE=clamav docker compose --profile security up --build
```

## Operations and observability

`/health/live` is a process liveness probe, while `/health/ready` actively checks
PostgreSQL, Redis, and MinIO and returns 503 if a required dependency is unavailable.
The backend's internal `/metrics` route exposes Prometheus-format metrics and is
blocked at the public gateway. Every HTTP response carries an `X-Request-ID`, which
is also included in structured JSON logs and exported spans.

Tracing is enabled only when `OTEL_EXPORTER_OTLP_TRACES_ENDPOINT` points to an
OTLP/HTTP traces endpoint. Prometheus is configured to discover all Compose backend
replicas rather than scraping only the gateway. See [the operations runbook](docs/operations.md)
for alert triage, scanner behavior, backup/restore drills, and secret rotation.

### Token behavior

Access tokens are short-lived JWTs. A refresh JWT contains a unique token ID (`jti`) that is also stored in PostgreSQL. Refreshing revokes the old row before issuing the next pair, preventing replay. Logout revokes the presented refresh token. Existing access tokens remain valid until their short expiry; immediate access-token revocation is deferred until there is a demonstrated need for it.

## Database migrations

Run migrations from `backend/` with a reachable database URL:

```bash
alembic upgrade head
alembic current
alembic downgrade -1
```

Create a migration after changing imported SQLAlchemy models:

```bash
alembic revision --autogenerate -m "describe the change"
```

Always inspect autogenerated migrations before applying them.

## Tests and checks

Backend tests use isolated in-memory SQLite databases for speed; migration and Compose validation cover the PostgreSQL wiring.

```bash
cd backend
../.venv/bin/ruff check .
../.venv/bin/pytest -q
```

```bash
cd frontend
npm run lint
npm run typecheck
npm test
npm run build
```

## WebSocket protocol

Connect to `WS /ws` with two WebSocket subprotocol values: `access_token` followed by the JWT access token. The browser client does this with `new WebSocket(url, ['access_token', token])`. This avoids placing credentials in URLs and common access logs. The server negotiates the `access_token` protocol and rejects missing, invalid, or expired access tokens before accepting the connection.

Client event:

```json
{
  "type": "message.send",
  "request_id": "client-generated-id",
  "conversation_id": "uuid",
  "content": "Hello",
  "attachment_ids": ["attachment-uuid"]
}
```

Clients can also send `typing.start`, `typing.stop`, and `message.read` events. Typing
events contain a `conversation_id`; a read event contains the conversation and latest
visible message IDs. The server verifies membership for every event.

Successful server event:

```json
{
  "type": "message.created",
  "request_id": "client-generated-id",
  "data": {
    "id": "uuid",
    "conversation_id": "uuid",
    "sender_id": "uuid",
    "sender_username": "alice",
    "content": "Hello",
    "created_at": "timestamp",
    "edited_at": null,
    "cursor": "opaque-cursor",
    "attachments": [
      {
        "id": "attachment-uuid",
        "filename": "photo.png",
        "mime_type": "image/png",
        "file_size": 12345,
        "uploaded_at": "timestamp",
        "download_url": "/attachments/attachment-uuid/download"
      }
    ],
    "receipts": [
      {
        "user_id": "recipient-uuid",
        "delivered_at": null,
        "read_at": null
      }
    ]
  }
}
```

Server-pushed state changes use `presence.online`, `presence.offline`, `typing.start`,
`typing.stop`, `message.delivered`, and `message.read`. `connection.ready` includes the
currently online conversation peers. Invalid or unauthorized events return a typed
`error` event with the originating `request_id` when available. A message is broadcast
to every active connection for each member, including the sender's other tabs, only
after PostgreSQL commits.

The browser reconnects with exponential backoff. After a successful reconnection, it uses the last durable message cursor with the REST `after` parameter, merges recovered records into the Zustand realtime store, and deduplicates them by message UUID.

## Engineering decisions

- **WebSockets for events, REST for resources:** REST remains cacheable and easy to paginate; WebSockets provide low-latency server push without polling.
- **Subprotocol authentication:** access tokens are carried in `Sec-WebSocket-Protocol`, avoiding query-string token leakage. A future cookie-based deployment can replace this without changing event payloads.
- **Persist then publish:** `message.send` reuses the same authorization and persistence service as REST. A failed transaction never produces `message.created`.
- **Direct upload, authorized download:** attachment bytes bypass the API on upload through a short-lived presigned URL, but reads are streamed by the API after conversation membership is checked.
- **Private objects and durable metadata:** MinIO objects are not public. PostgreSQL tracks ownership, conversation scope, expected size/type, upload completion, and the single message binding.
- **Transactional attachment binding:** row locks prevent two messages from claiming the same attachment, and message creation commits the binding atomically.
- **Distributed garbage collection:** one backend at a time claims a Redis lock and removes expired, unbound objects in bounded batches.
- **Fail-closed scan boundary:** when ClamAV scanning is enabled, an object cannot be finalized or attached unless the scanner returns a clean result.
- **Immutable delivery object:** finalization copies the verified ETag away from the presigned staging key, so a still-valid upload URL cannot replace a scanned attachment.
- **Bounded telemetry labels:** HTTP metrics use route templates rather than raw paths, preventing user-controlled IDs from creating unbounded Prometheus series.
- **Probe separation:** liveness observes only the process; readiness gates traffic on required durable and coordination dependencies.
- **PostgreSQL as source of truth:** a message is delivered as a durable event only after it has been authorized and persisted. Redis will never be the canonical message store.
- **Durable receipts, ephemeral activity:** delivered/read timestamps and `last_seen` live in PostgreSQL. Redis stores only replaceable Pub/Sub messages, leases, typing expirations, and rate-limit counters.
- **Distributed presence semantics:** sorted-set leases represent each instance serving a user. Only the first global connection emits online, and only the last global disconnection emits offline. A surviving instance detects expired crash leases.
- **Distributed typing expiry:** Redis stores typing deadlines and event targets. Atomic claiming ensures exactly one surviving instance publishes the expiry event.
- **Graceful degradation:** non-required local development can fall back to in-process routing when Redis is unavailable. Compose and production-style deployments set `REDIS_REQUIRED=true`.
- **Refresh rotation:** server-side token records make logout and replay prevention possible without storing raw tokens.
- **UUID identifiers:** IDs can be created safely across future application instances without relying on a central sequence.
- **Redis is not canonical:** Pub/Sub can be lossy by design because cursor recovery closes message gaps after reconnect. PostgreSQL remains authoritative.
- **Ordering and recovery:** message history is ordered by `(created_at, id)` and uses that pair as an opaque cursor. Reconnecting clients request records after their last durable cursor, covering gaps during disconnects.

## Project structure

```text
.
├── .github/workflows/ci.yml
├── .env.example
├── docker-compose.yml
├── docs/operations.md            # alerts, scanning, backup/restore, rotation
├── gateway/nginx.conf            # REST and WebSocket load-balancing gateway
├── observability/                # Prometheus scrape configuration and alerts
├── backend
│   ├── alembic/
│   │   ├── env.py
│   │   └── versions/             # users, messaging, receipts, and attachments
│   ├── app
│   │   ├── api/                 # HTTP routes and dependencies
│   │   ├── core/                # configuration, database, errors, security
│   │   ├── models/              # SQLAlchemy persistence models
│   │   ├── repositories/        # database queries
│   │   ├── schemas/             # external request/response contracts
│   │   ├── services/             # application transactions and cleanup workers
│   │   └── main.py
│   ├── tests/test_auth.py
│   ├── Dockerfile
│   └── pyproject.toml
└── frontend
    ├── src
    │   ├── api/
    │   ├── components/
    │   ├── pages/
    │   ├── stores/
    │   ├── test/
    │   ├── types/
    │   └── App.tsx
    ├── Dockerfile
    └── package.json
```

## Next increment

Add group conversations and roles, including membership changes, authorization
rules, system events, and frontend group-management flows.
