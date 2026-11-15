# Backend Helm chart

Deploys the FastAPI backend and a ClusterIP Service on port `8000`. A separate Job runs `alembic upgrade head` before Helm install/upgrade or as an Argo CD `PreSync` hook. A failed migration blocks the deployment. Failed Jobs remain for inspection until the next attempt; successful Jobs are removed.

PostgreSQL and an existing Secret containing `IDEA_BOARD_DATABASE_URL` must be provisioned before installing this chart. Use a `postgresql+psycopg://` URL. Both the backend and migration Job read that key directly as an environment variable. The chart does not provision PostgreSQL.

## Install

```bash
helm upgrade --install backend charts/idea-board-backend \
  --namespace idea-board \
  --set databaseSecretName=idea-board-database \
  --set image.repository=ghcr.io/rohitraut3366/idea-board-backend \
  --set image.tag=YOUR_COMMIT \
  --wait --timeout 5m
```

For local kind, use `--kube-context kind-idea-board` and `-f gitops/kind/backend-values.yaml` instead of the image overrides. Those values point to the published GHCR commit tag.

The Service name matches the Helm release name: `backend` in this example. The frontend chart defaults to connecting to `backend:8000` in the same namespace. The charts are separate releases and can be upgraded independently.

```bash
helm test backend --namespace idea-board --logs --timeout 2m
```

The backend smoke test checks health, creates an idea, reads it, and deletes it. Use a test environment for smoke checks.

## Configuration

| Value                | Default              | Purpose                                                |
| -------------------- | -------------------- | ------------------------------------------------------ |
| `databaseSecretName` | Required             | Existing Secret with `IDEA_BOARD_DATABASE_URL`         |
| `image.repository`   | `idea-board-backend` | Container repository                                   |
| `image.tag`          | `local`              | Image tag; use a commit tag for published images       |
| `image.pullPolicy`   | `IfNotPresent`       | Image pull policy                                      |
| `replicas`           | `1`                  | Backend replicas                                       |
| `resources`          | See `values.yaml`    | Backend and migration Job resource requests and limits |

Readiness uses `/health`; startup and liveness use TCP probes. A database outage removes traffic without repeatedly restarting healthy API processes. Pods run as non-root, disable privilege escalation, and do not mount service-account tokens.

The database and Secret must already exist before an Argo CD sync reaches the migration hook. Helm rollback restores application manifests, not database migrations; migrations must remain compatible with the previous application version.

## Checks

```bash
helm lint charts/idea-board-backend --strict --set databaseSecretName=idea-board-database
```

GitHub Actions installs this chart into kind, runs the smoke test, upgrades it to rerun migrations, and repeats the smoke test. `tests/postgres.yaml` is an ephemeral database fixture for those CI tests; it is not installed by the chart and is not a persistent development database.

The deployment tool sets `databaseRevision` to a hash of the database connection configuration. A changed credential Secret then changes the pod template and rolls out backend pods so they read the current environment value. The Secret value itself is not included in the Application or Helm values.

## Ingress health configuration

The frontend chart's Ingress routes `/api` directly to this backend Service. AWS values set the Service's `alb.ingress.kubernetes.io/healthcheck-path` to `/health`. GCP values annotate the Service for a network endpoint group and its BackendConfig; `gcpBackendConfig: true` creates that health configuration with path `/health` on pod port 8000. The backend chart does not create another Ingress or a public Service. See the [ingress guide](../../infra/ingress/README.md) for setup and ownership.
