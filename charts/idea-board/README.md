# Idea Board Helm chart

Deploys the backend and web app with ClusterIP Services. Nginx proxies `/api` to the backend Service. A separate Job runs `alembic upgrade head` before Helm installs or upgrades workloads, or as an Argo CD `PreSync` hook. A failed migration blocks that deployment. Successful migration Jobs are removed; failed Jobs remain for inspection until the next attempt.

PostgreSQL and its credentials must exist before installing the chart. The chart does not create a database, public routing, or TLS certificates.

## Install

Build and publish both application images from the same commit. Create a Secret in the target namespace containing the `IDEA_BOARD_DATABASE_URL` key, with a `postgresql+psycopg://` connection URL. Both the backend and migration Job read that key as an environment variable.

```bash
helm upgrade --install board ./charts/idea-board \
  --namespace idea-board --create-namespace \
  --set backend.databaseSecretName=idea-board-database \
  --set backend.image.repository=YOUR_REGISTRY/idea-board-backend \
  --set backend.image.tag=YOUR_COMMIT \
  --set frontend.image.repository=YOUR_REGISTRY/idea-board-frontend \
  --set frontend.image.tag=YOUR_COMMIT \
  --wait --timeout 5m
```

The Secret must be provisioned separately before the migration hook runs, including on the first Argo CD sync. When using Argo CD, sync this chart after database and Secret provisioning. The chart smoke test is run by `helm test`; Argo CD skips that test Pod.

For a release named `board`:

```bash
kubectl --namespace idea-board port-forward service/board-idea-board-frontend 3000:80
helm test board --namespace idea-board --logs --timeout 2m
```

Open `http://localhost:3000`. The smoke test creates an idea, reads it through the frontend proxy, and deletes it. Run it against a disposable test environment.

## Configuration

| Value | Default | Purpose |
| --- | --- | --- |
| `backend.databaseSecretName` | Required | Existing Secret with `IDEA_BOARD_DATABASE_URL` |
| `backend.image.repository` / `frontend.image.repository` | `idea-board-backend` / `idea-board-frontend` | Container repositories |
| `backend.image.tag` / `frontend.image.tag` | `local` | Image tags; use a commit tag for published images |
| `backend.image.pullPolicy` / `frontend.image.pullPolicy` | `IfNotPresent` | Container pull policy |
| `backend.replicas` / `frontend.replicas` | `1` | Deployment replicas |
| `backend.resources` / `frontend.resources` | See `values.yaml` | Container resource requests and limits |

The migration Job uses the backend image and resource settings. The backend uses `/health` for readiness and TCP probes for startup and liveness, so a database outage removes traffic without repeatedly restarting healthy API processes. The frontend uses `/` for its probes. Pods run as non-root with privilege escalation disabled and service-account token mounting disabled.

Helm rollback restores application manifests; it does not undo database migrations. Keep migrations compatible with the previous application version before upgrading.

## Test with kind

Run from the repository root. These commands use a dedicated kubeconfig and do not change your current Kubernetes context.

```bash
docker compose build backend frontend
kind create cluster --name idea-board --image kindest/node:v1.33.1 \
  --kubeconfig /tmp/idea-board-kubeconfig
export KUBECONFIG=/tmp/idea-board-kubeconfig
kind load docker-image idea-board-backend:local idea-board-frontend:local --name idea-board
kubectl create namespace idea-board
kubectl --namespace idea-board apply -f charts/idea-board/tests/postgres.yaml
kubectl --namespace idea-board rollout status deployment/postgres --timeout=2m
helm lint charts/idea-board --strict --set backend.databaseSecretName=idea-board-database
helm upgrade --install board charts/idea-board --namespace idea-board \
  --set backend.databaseSecretName=idea-board-database --wait --timeout 5m
helm test board --namespace idea-board --logs --timeout 2m
```

`tests/postgres.yaml` supplies an ephemeral test database and local-only credentials. It is not part of the installed chart. Test the upgrade hook by running the Helm upgrade command and smoke test a second time. GitHub Actions runs the same install, upgrade, and smoke checks in kind.

Remove the test cluster when finished:

```bash
kind delete cluster --name idea-board
unset KUBECONFIG
```
