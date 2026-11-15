# Frontend

React and TypeScript for the Idea Board. The app displays ideas, submits plain text, and loads older ideas in pages of 50. Nginx serves the built files and forwards `/api` requests to the backend.

## Run the complete app

From the repository root:

```bash
make up
```

Open `http://localhost:3000`. Compose starts PostgreSQL, runs the migration service, waits for the backend to become healthy, and starts the frontend.

## Develop the frontend

Use Node 24. From this directory:

```bash
npm ci
npm run dev
```

Vite prints the local address and proxies `/api` to `http://127.0.0.1:8000`. Start the backend through Compose or follow the backend README. No CORS configuration or build-time API URL is needed. The Nginx container uses `BACKEND_UPSTREAM`, which defaults to `backend:8000` for Compose. Helm supplies the full backend Service address. Nginx refreshes the address through DNS so it follows a replaced backend container.

## Behavior

- Ideas appear newest first. “Load more ideas” follows the backend’s cursor without shifting older pages when new ideas arrive.
- Submissions accept 1–2,000 characters after trimming whitespace. Emoji count as single Unicode code points, matching the backend.
- Exact duplicate text is rejected after trimming; capitalization remains significant. The draft stays in the form when a duplicate is rejected.
- Each idea has a Delete action with an inline confirmation. The card stays visible until deletion is confirmed. If another visitor has already deleted it, the stale card is removed.
- A new idea appears after the server confirms it. A failed request keeps the draft. Use “Refresh ideas” to check whether a write committed before submitting again; writes are never retried automatically.
- Read failures show a retry button. A failed older-page request keeps the ideas already loaded.
- Idea content renders as text. The form and status messages use labels and accessible announcements. The layout adapts to narrow screens without a separate mobile view.

## Checks

```bash
npm test
npm run typecheck
npm run build
npm run format:check
```

Tests live in `tests/` and exercise the rendered app with simulated API responses. They cover submissions, failed writes, read retries, pagination, plain-text rendering, large IDs, character limits, duplicate messages, deletion confirmation, and failed deletion. `npm run typecheck` checks the application and test code; `npm run build` produces the static assets. The full-stack HTTP and load checks are separate from the component suite; none of these local tests establish cloud capacity. Browser-driven E2E testing remains pending.

With a running stack, `npm run test:stack` checks the built assets, API proxy, writes, validation, pagination, duplicate rejection, and deletion over HTTP. It creates two ideas and deletes them on success; use a disposable test stack. Set `IDEA_BOARD_BASE_URL` to target a different address.

The Docker build excludes tests and installs dependencies before copying application code. Editing a test does not rebuild the production image. Local builds reuse an npm download cache; GitHub Actions also restores the image layers and the frontend test job’s npm cache.

## Concurrency checks

With a running Compose stack, run `npm run test:load`. Set `LOAD_CYCLES`, `LOAD_CONCURRENCY`, and `IDEA_BOARD_BASE_URL` to choose the workload and target. `LOAD_MAX_P95_MS` optionally enforces a request-latency target. The command reports errors, throughput, p95 request latency, and cleanup failures. It deletes the ideas it created and received IDs for, even after a subsequent read fails. The load runner's own tests exercise successful runs and injected read failures.
