# Operations runbook

This runbook covers the production-style controls included with Chatterbox. The
Compose stack is a reference deployment, not a substitute for managed secrets,
TLS termination, encrypted backups, or an orchestrator in a public environment.

## Health and traffic

- `GET /health/live` proves the API process can serve requests. It intentionally
  does not check dependencies and is suitable for a liveness probe.
- `GET /health/ready` actively checks PostgreSQL, Redis, and MinIO. It returns
  HTTP 503 when a required dependency is unavailable and is suitable for a
  readiness probe.
- `GET /health` is a compatibility alias for the readiness check.
- Every HTTP response includes `X-Request-ID`. A valid inbound ID is preserved;
  otherwise the API generates one. Logs include that value for correlation.

Do not put readiness probes on the public edge unless operational dependency
status is intended to be visible. The response exposes service categories, not
credentials or connection strings.

## Logs, metrics, and traces

Application and request logs are one-line JSON on stdout; process startup messages
remain in Uvicorn's standard format. Request logs contain the route template, method,
status, duration, client address, request ID, and active trace ID. They do not log
authorization headers, cookies, query strings, or request bodies.

Prometheus runs at <http://localhost:9090> in Compose and discovers every backend
replica through Docker DNS. The backend exposes `/metrics` with bounded
route-template labels, but the included gateway blocks that route from its public
listener. Important series include:

- `chatterbox_http_requests_total`
- `chatterbox_http_request_duration_seconds`
- `chatterbox_http_requests_in_progress`
- `chatterbox_websocket_connections`
- `chatterbox_websocket_events_total`
- `chatterbox_attachment_scans_total`

Alert rules in `observability/alerts.yml` cover unavailable API replicas, elevated
5xx rates, high p95 latency, and scanner failures. Route the rules through an
Alertmanager (or import equivalent expressions into the deployed monitoring
system) before treating them as paging alerts.

Tracing is off until `OTEL_EXPORTER_OTLP_TRACES_ENDPOINT` is set to an OTLP/HTTP
traces endpoint, usually ending in `/v1/traces`. FastAPI and SQLAlchemy spans are
then exported with the configured service name. Health and metrics routes are
excluded. Keep the exporter on a private network and apply retention and access
controls at the collector/backend.

### First-response checklist

1. Find the request by `X-Request-ID`, then use its `trace_id` to inspect the
   distributed trace when tracing is enabled.
2. Compare the 5xx rate and latency by route, then check PostgreSQL, Redis, and
   MinIO using `/health/ready` from inside the deployment network.
3. For an instance-down alert, distinguish a failed scrape from a failed process
   in Prometheus **Status > Targets**.
4. For scanner alerts, stop finalizing uploads until ClamAV is healthy. Pending
   objects remain private and cannot be attached to messages.

## Attachment malware scanning

Scanning is disabled by default so local development has no hidden external
dependency. Enable the included ClamAV service with:

```bash
ATTACHMENT_SCAN_MODE=clamav docker compose --profile security up --build
```

The API streams the object from private MinIO to `clamd` using its INSTREAM
protocol after size/type verification. It then conditionally copies that exact
ETag from the mutable staging key to a separate delivery key before marking the
upload complete. A still-valid presigned upload URL therefore cannot replace the
scanned object. A concurrent replacement returns `ATTACHMENT_CHANGED`, an infected
file returns `ATTACHMENT_INFECTED`, and scanner downtime fails closed with
`ATTACHMENT_SCAN_UNAVAILABLE`. In each failure case the object stays unbound and
private until abandoned-upload cleanup removes it. Tune the ClamAV timeout above
the worst expected scan time and monitor the scan outcome counter.

## Backup and restore

Take PostgreSQL and MinIO backups within the same maintenance window because the
database owns attachment metadata while MinIO owns the corresponding bytes. Store
backups encrypted outside the deployment and test restoration regularly. Redis
holds recoverable coordination state only, so it is normally rebuilt rather than
restored.

### PostgreSQL

Create a custom-format dump:

```bash
docker compose exec -T postgres pg_dump -U chat -d chat -Fc > chatterbox-postgres.dump
```

Restore into a newly created, empty database after stopping API writers:

```bash
docker compose exec -T postgres createdb -U chat chatterbox_restore
docker compose exec -T postgres pg_restore -U chat -d chatterbox_restore --no-owner --no-privileges < chatterbox-postgres.dump
docker compose exec -T postgres psql -U chat -d chatterbox_restore -c 'SELECT count(*) FROM alembic_version;'
```

Point a non-public API instance at the restored database and exercise registration,
login, conversation history, and attachment authorization before promoting it.
Run `alembic current` and apply only migrations that are newer than the restored
dump.

### MinIO

Configure `mc` with a read-only backup credential where possible, then mirror the
private bucket to encrypted backup storage:

```bash
mc mirror --overwrite chatterbox/chat-attachments backup/chatterbox/chat-attachments
```

Restore to a new private bucket first:

```bash
mc mirror --overwrite backup/chatterbox/chat-attachments restore/chat-attachments
```

Confirm the restored bucket has no anonymous policy. Compare a sample of object
keys and sizes against PostgreSQL attachment rows, then test authorized and
unauthorized downloads through the API. Do not expose the bucket to make a restore
test easier.

### Redis

Redis Pub/Sub messages, presence leases, typing state, rate-limit counters, and
cleanup locks can be discarded. After a loss, restart Redis and then the API
instances. Clients reconnect and recover durable messages from PostgreSQL using
their cursors. The Compose AOF volume improves local restart behavior but is not a
substitute for backing up canonical data.

### Restore drill acceptance criteria

- The restored schema reports the expected Alembic revision.
- User, conversation, message, receipt, and attachment row counts are plausible.
- A known user can authenticate and paginate message history.
- A known attachment downloads for a member and is denied to a non-member.
- Redis can start empty without losing durable messages.
- Readiness is green and Prometheus sees all intended API replicas.

## Secret rotation

- Rotate database and MinIO credentials by creating a second credential, updating
  all API instances, verifying readiness, and only then revoking the old one.
- Rotating `JWT_SECRET` immediately invalidates all outstanding access and refresh
  JWTs. Schedule it as a forced sign-in event unless dual-key verification is
  implemented first.
- Keep OTLP and monitoring credentials outside Compose files. Prefer a deployment
  secret manager and avoid injecting secrets into command-line arguments or logs.
- After any rotation, search logs for authentication failures, verify readiness,
  and exercise a new login and attachment upload/download.
