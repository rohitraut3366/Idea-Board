# Deployment tool

This tool turns a validated Codex recommendation into two Argo CD Applications, prepares the database Secret, and waits for a working release. It is shared by the GitHub Actions workflow and local execution.

## Local use

Install Python 3.12, uv, Helm, kubectl, Node.js, and Codex CLI. Use an existing Kubernetes cluster with Argo CD and publicly readable app images. The tool always requires an explicit kube context for mutations.

From the repository root, set the full published image and chart commit SHAs. They may differ for a local verification run, but the cloud workflow uses the same tested source commit for both:

```bash
export IMAGE_TAG=FULL_40_CHARACTER_IMAGE_COMMIT_SHA
export CHART_REVISION=FULL_40_CHARACTER_CHART_COMMIT_SHA
uv sync --project tools/deploy --locked --all-groups

python tools/deploy/deploy.py prompt \
  --cloud kind --environment staging \
  --image-tag "$IMAGE_TAG" --revision "$CHART_REVISION" \
  --request 'Low-traffic staging for a few reviewers' > /tmp/idea-board-deployment-prompt.md

codex exec --sandbox read-only --ephemeral \
  --output-schema .agents/skills/deploy/output.schema.json \
  --output-last-message /tmp/idea-board-recommendation.json \
  - < /tmp/idea-board-deployment-prompt.md

python tools/deploy/deploy.py render \
  --cloud kind --environment staging \
  --image-tag "$IMAGE_TAG" --revision "$CHART_REVISION" \
  --recommendation /tmp/idea-board-recommendation.json
```

Review the recommendation and rendered Applications. For a local kind release, export `IDEA_BOARD_DATABASE_URL` for a database reachable **from the cluster**, then replace `render` with `release` and add `--context kind-idea-board`. Use `uv run --project tools/deploy python tools/deploy/deploy.py` for `release` and `cleanup`, which need psycopg. No `.env` file is read. Never point a local staging test at a production database.

Local staging uses namespace `idea-board-staging`, leaving the existing `idea-board` namespace separate. The tool creates new namespaces with ownership labels and refuses to adopt unrelated existing namespaces. A local PostgreSQL instance must already be provisioned; the tool does not create a Kubernetes database server. Ports and database names depend on that setup.

For a preview, pass `--environment preview --pr 123`. Staging must already be healthy because database operations execute inside its backend. Cloud releases fetch managed credentials using the Environment variables listed in the [root README](../../README.md).

## Preview cleanup

The close-PR workflow runs cleanup automatically. To retry it manually, run Deploy with `environment=preview`, the original PR number, and `operation=cleanup`. No model call is needed. The tool rejects automated cleanup for staging or production. The cloud cleanup uses the staging cluster and database identity, not a separate Terraform stack per PR.

## Tests

Run with the existing local Compose PostgreSQL service available:

```bash
uv run --project tools/deploy --locked ruff check tools/deploy
uv run --project tools/deploy --locked ruff format --check tools/deploy
uv run --project tools/deploy --locked mypy tools/deploy --check-untyped-defs --ignore-missing-imports
uv run --project tools/deploy --locked pytest tools/deploy/tests
```

Tests create uniquely named preview databases and roles on the local test PostgreSQL server, then remove them. Set `IDEA_BOARD_TEST_DATABASE_URL` to use another dedicated test server whose identity can create and delete databases and roles. Tests cover profile validation, generated chart rendering, stale rollout status, namespace ownership, preview persistence/cleanup, refusal to delete unrelated databases, and fork/stale-PR filtering.

No test substitutes a fixed profile for a live Codex result while claiming a model call occurred. Live model authentication, cloud OIDC trust, managed PostgreSQL role permissions, and external load-balancer behavior need separate verification in the target accounts.

For the full local Argo check, use an existing test kind cluster with Argo CD and the chart test PostgreSQL Deployment/Secret in namespace `idea-board`:

```bash
uv run --project tools/deploy python tools/deploy/tests/check_kind.py \
  --context kind-idea-board --image-tag "$IMAGE_TAG" --revision "$CHART_REVISION"
```

This check refuses to use existing staging or test-preview namespaces and databases. It creates isolated test resources, verifies staging, preview migration/deployment, preview redeployment, HTTP access, and cleanup, then removes only what it created. The current chart commit must be reachable from the public Git repository because Argo CD fetches it there. CI runs this check after publishing the tested images.
