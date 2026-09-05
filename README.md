# Chatterbox

Chatterbox is a production-minded realtime chat application being built incrementally as a modular monolith. This repository currently contains the **Phase 1 realtime messaging MVP**: an asynchronous FastAPI API backed by PostgreSQL, secure token-based authentication, direct conversations, persisted message history, authenticated WebSocket delivery, reconnect recovery, a responsive React chat workspace, migrations, tests, containers, and CI.

Realtime delivery currently uses an in-process connection manager. Redis and MinIO are included in the local stack so the infrastructure contract is stable, but application code does not use them yet.

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
- Authenticated `WS /ws` connections using the WebSocket subprotocol header
- Typed `message.send`, `message.created`, connection, and error events
- Member-targeted delivery after successful database commit
- Automatic reconnect with exponential backoff up to 30 seconds
- Post-cursor REST recovery for messages missed while disconnected
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
    Browser[React + Ant Design] -->|REST / JSON| API[FastAPI routes]
    API --> Services[Application services]
    Services --> Repos[Repositories]
    Repos --> DB[(PostgreSQL)]
    Browser <-->|Typed realtime events| WS[WebSocket gateway]
    WS --> Services
    WS -. scale-out phase .-> Redis[(Redis Pub/Sub)]
    Services -. attachment phase .-> MinIO[(MinIO)]
```

The backend is a layered modular monolith. Routes handle HTTP concerns, services own business transactions, repositories contain database queries, schemas define external contracts, and SQLAlchemy models define persistence. PostgreSQL is the source of truth; ephemeral delivery state will live in Redis only after the single-instance realtime path works.

## Technology stack

| Area | Technology |
| --- | --- |
| API | Python, FastAPI, Pydantic |
| Persistence | PostgreSQL, async SQLAlchemy, Alembic |
| Authentication | Argon2 via pwdlib, signed JWTs, persisted refresh-token JTIs |
| Web | React, strict TypeScript, Vite, Ant Design |
| Client state | TanStack Query, Zustand |
| Infrastructure | Docker Compose, Redis, MinIO, Nginx |
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

Open:

- Web app: <http://localhost:3000>
- API documentation: <http://localhost:8000/docs>
- API health check: <http://localhost:8000/health>
- MinIO console: <http://localhost:9001>

The backend waits for PostgreSQL, applies `alembic upgrade head`, and then starts Uvicorn. Stop the stack with `docker compose down`. Volumes are retained; `docker compose down -v` also removes local development data.

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
| `REDIS_URL` | Reserved for realtime scale-out | `redis://redis:6379/0` |
| `MINIO_ROOT_USER` | Local object-storage administrator | `minioadmin` |
| `MINIO_ROOT_PASSWORD` | Local object-storage password | Development-only value |
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

Errors have one stable envelope:

```json
{
  "error": {
    "code": "INVALID_CREDENTIALS",
    "message": "Invalid login or password"
  }
}
```

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
  "content": "Hello"
}
```

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
    "cursor": "opaque-cursor"
  }
}
```

Invalid or unauthorized events return a typed `error` event with the originating `request_id` when available. A message is broadcast to every active connection for each member, including the sender's other tabs, only after PostgreSQL commits.

The browser reconnects with exponential backoff. After a successful reconnection, it uses the last durable message cursor with the REST `after` parameter, merges recovered records into the Zustand realtime store, and deduplicates them by message UUID.

## Engineering decisions

- **WebSockets for events, REST for resources:** REST remains cacheable and easy to paginate; WebSockets provide low-latency server push without polling.
- **Subprotocol authentication:** access tokens are carried in `Sec-WebSocket-Protocol`, avoiding query-string token leakage. A future cookie-based deployment can replace this without changing event payloads.
- **Persist then publish:** `message.send` reuses the same authorization and persistence service as REST. A failed transaction never produces `message.created`.
- **PostgreSQL as source of truth:** a message is delivered as a durable event only after it has been authorized and persisted. Redis will never be the canonical message store.
- **Refresh rotation:** server-side token records make logout and replay prevention possible without storing raw tokens.
- **UUID identifiers:** IDs can be created safely across future application instances without relying on a central sequence.
- **Redis is deliberately idle today:** the MVP should prove one-process connection management first. In the scale-out phase, instances will publish user-targeted events so recipients connected to a different process receive them.
- **Ordering and recovery:** the message phase will order history by `(created_at, id)` and use that pair as an opaque cursor. Reconnecting clients will request records after their last durable cursor, covering gaps during disconnects.

## Project structure

```text
.
├── .github/workflows/ci.yml
├── .env.example
├── docker-compose.yml
├── backend
│   ├── alembic/
│   │   ├── env.py
│   │   └── versions/20260905_0001_create_users.py
│   ├── app
│   │   ├── api/                 # HTTP routes and dependencies
│   │   ├── core/                # configuration, database, errors, security
│   │   ├── models/              # SQLAlchemy persistence models
│   │   ├── repositories/        # database queries
│   │   ├── schemas/             # external request/response contracts
│   │   ├── services/            # authentication business logic
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

Add presence, typing indicators, delivered status, read receipts, and unread counts on top of the typed event protocol. Keep these ephemeral features in memory for one instance first; once their semantics and tests are stable, introduce Redis Pub/Sub and presence keys for horizontal scaling.
