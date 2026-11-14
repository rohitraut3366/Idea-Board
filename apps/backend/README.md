# Backend

FastAPI and PostgreSQL for the Idea Board. The repository root has one `docker-compose.yml` for the frontend, backend, migration job, and PostgreSQL. Cloud deployment remains planned.

## Run locally

Run from the repository root with a Docker-compatible engine and Compose support:

```bash
docker compose up --build --wait
```

Compose waits for PostgreSQL to be healthy, runs `alembic upgrade head` in the separate `migrate` service, and starts the backend only when that service exits successfully. A failed migration blocks backend startup. The API checks the database and required table columns on startup and exits with an error if either is unavailable. It never runs migrations.

The API is available at `http://127.0.0.1:8000`; interactive API documentation is at `/docs`. PostgreSQL listens on loopback port `55432`. Its credentials in the root `docker-compose.yml` are local development values. Use a different database URL and credentials outside this setup.

The database volume survives `docker compose down`; `docker compose down --volumes` deletes local data. To inspect migration failures, run `docker compose logs migrate`.

For development outside the backend container, install uv and Python 3.12, then run from `apps/backend`:

```bash
export IDEA_BOARD_DATABASE_URL=postgresql+psycopg://idea_board:idea_board_local@127.0.0.1:55432/idea_board
docker compose -f ../../docker-compose.yml up -d --wait postgres
uv sync --locked --all-extras --all-groups
uv run alembic upgrade head
uv run uvicorn idea_board.server:create_app --factory --host 127.0.0.1 --port 8000
```

Stop the Compose backend with `docker compose -f ../../docker-compose.yml stop backend` before starting a host process on the same port. Apply migrations before starting either process.

```bash
curl -X POST http://127.0.0.1:8000/api/ideas \
  -H 'Content-Type: application/json' \
  -d '{"content":"Make deployments easier to investigate"}'
curl http://127.0.0.1:8000/api/ideas
curl 'http://127.0.0.1:8000/api/ideas?limit=50'
```

## API

| Endpoint | Result |
| --- | --- |
| `POST /api/ideas` | Commit one idea with `201`; return `409` for duplicate text |
| `DELETE /api/ideas/{id}` | Delete one idea with `204`; return `404` if it is already absent |
| `GET /api/ideas` | Return every idea, newest ID first |
| `GET /api/ideas?limit=50` | Return a page and a `Link` header when older ideas exist |
| `GET /api/ideas?limit=50&before_id=42` | Return ideas with IDs below the cursor |
| `GET /health` | `200` with `{"status":"ok"}` when the ideas table is accessible; `503` otherwise |

Both list variants return JSON arrays. IDs are decimal strings; timestamps are in UTC. New submissions do not shift older pages because pagination uses IDs rather than offsets. Pagination is not a snapshot across requests.

Content is trimmed and must contain 1–2,000 characters. Exact duplicate text is rejected after trimming; comparison is case-sensitive. PostgreSQL enforces this through a hash exclusion constraint, which supports long Unicode text without a B-tree index-key limit. Concurrent duplicate requests create one row and return `409` for the others. Blank content, NUL characters, invalid Unicode, extra fields, and invalid pagination return `422`. `limit` accepts 1–100; `before_id` requires a limit and must fit a positive PostgreSQL bigint.

Database connection failures, query timeouts, and pool exhaustion return `503` without database details or submitted content. A failed POST response or a client timeout does not establish whether a write committed. Clients must not automatically retry writes; this API does not provide idempotency keys.

The API permits anonymous submissions and deletion. Any visitor can delete an idea. Public routing, TLS termination, write-rate limiting, and metrics are later platform steps. Run this first step on loopback.

## Configuration

The backend and migration job read `IDEA_BOARD_DATABASE_URL` directly from the process environment in every environment. Compose supplies it locally; when running on the host, export it as shown above. Use a `postgresql+psycopg://` URL. SQLAlchemy manages the connection pool with its defaults.

Use URL query parameters such as `sslmode=verify-full` and `sslrootcert` when connecting to a remote database. The local Compose database does not enable TLS. A missing database URL fails startup. Startup also fails if the database or required schema is unavailable. Run one worker initially; each additional worker creates another pool.

## Tests and checks

All backend tests live in `tests/`. Unit tests do not need PostgreSQL. Integration tests require a running PostgreSQL server and create a uniquely named temporary database, apply the actual Alembic migration, and delete that database afterward. They do not truncate the development database.

```bash
uv run --all-extras --all-groups pytest
uv run --all-extras --all-groups mypy
uv run --all-extras --all-groups ruff check .
uv run --all-extras --all-groups ruff format --check .
```

Integration tests use the local Compose connection by default. Set `IDEA_BOARD_TEST_DATABASE_URL` to use another PostgreSQL server. That identity must be able to create and delete databases on a dedicated test server. Missing PostgreSQL fails the integration suite; it is not silently skipped.

```bash
uv run pytest tests/unit
uv run pytest tests/integration
```

The integration suite covers API behavior, keyset pagination, concurrent writes, persistence across application restarts, the migration lifecycle, duplicate rejection under concurrent writes, long Unicode content, deletion, and an unavailable database. The full cloud scale tests remain a separate implementation step.

The Docker build installs locked runtime dependencies before copying the README and application code. It reuses a uv download cache and copies only the installed environment and migration files into the runtime stage. Documentation and migration edits do not reinstall third-party dependencies.
