# Idea Board

A web app for sharing ideas, built with React, FastAPI, and PostgreSQL. Submit an idea, browse recent entries, load older ones, or delete an entry with confirmation.

## Run locally

Install Docker with Compose support, then run from the repository root:

```bash
docker compose up --build --wait
```

Open [Idea Board](http://localhost:3000). API documentation is available at [localhost:8000/docs](http://localhost:8000/docs).

Compose starts PostgreSQL, runs database migrations as a separate job, then starts the backend and frontend. A failed migration blocks backend startup. The backend also fails startup if the database or required schema is unavailable.

```bash
docker compose logs backend
docker compose down
```

The database volume survives shutdown. `docker compose down --volumes` deletes local data.

## How it works

Nginx serves the frontend and forwards `/api` requests to FastAPI. The backend stores ideas in PostgreSQL. Each idea has an ID, text, and creation time.

- Ideas appear newest first, with cursor pagination for older entries.
- Text must contain 1–2,000 characters after trimming whitespace.
- Exact duplicates are rejected; comparison is case-sensitive.
- Any visitor can submit or delete an idea. Deletion requires confirmation in the UI.
- Failed submissions retain the draft. Writes are never retried automatically.

| Service | Local address |
| --- | --- |
| Web app | `http://localhost:3000` |
| API | `http://localhost:8000` |
| PostgreSQL | `127.0.0.1:55432` |

The backend and migration job read `IDEA_BOARD_DATABASE_URL` from the process environment. Compose supplies local development credentials. Use environment-specific credentials for other deployments.

## Development and tests

See the [backend README](apps/backend/README.md) and [frontend README](apps/frontend/README.md) for host setup, API behavior, and test details. Tests live inside the app they verify.

Backend checks, from `apps/backend`, with the Compose PostgreSQL service running:

```bash
uv sync --locked --all-extras --all-groups
uv run --all-extras --all-groups pytest
uv run --all-extras --all-groups mypy
uv run ruff check .
uv run ruff format --check .
```

Frontend checks, from `apps/frontend`:

```bash
npm ci
npm test
npm run typecheck
npm run format:check
npm run build
```

With a disposable Compose stack running, `npm run test:stack` checks the frontend and API together over HTTP. Backend integration tests create and remove a temporary database without changing the development database.

GitHub Actions runs backend and frontend checks, builds both container images with cached layers, starts the Compose stack, runs full-stack HTTP tests, and verifies that migrations can run again.
