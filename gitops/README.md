# Run Idea Board in kind

Argo CD reads the deployment configuration from Git and keeps the cluster in sync. You install Argo CD and apply one root Application. That root creates PostgreSQL and the Applications below it:

```text
local
├── PostgreSQL: credentials, storage, Deployment and Service
├── ingress-controller → Traefik
└── idea-board
    ├── backend → FastAPI and its migration Job
    └── frontend → React, Nginx and the Ingress routes
```

The browser loads the web app at `localhost:8081`. Requests to `/api` reach the backend through Traefik. PostgreSQL is reachable inside the cluster.

Docker, kind, kubectl, Helm, Python, uv and Node.js are needed. Run the commands from the repository root.

## 1. Create the cluster

If `kind-idea-board` already exists, continue to step 2.

```bash
kind create cluster --name idea-board --config gitops/kind/config.yaml
kubectl --context kind-idea-board get nodes
```

The kind configuration maps local port `8081` to Traefik's NodePort.

## 2. Install Argo CD

```bash
kubectl --context kind-idea-board create namespace argocd
kubectl --context kind-idea-board apply --server-side -k gitops/argocd
kubectl --context kind-idea-board --namespace argocd rollout status deployment/argocd-server --timeout=5m
kubectl --context kind-idea-board --namespace argocd rollout status deployment/argocd-repo-server --timeout=5m
kubectl --context kind-idea-board --namespace argocd rollout status statefulset/argocd-application-controller --timeout=5m
```

If the namespace already exists, continue with the apply command.

## 3. Apply the root

```bash
kubectl --context kind-idea-board apply -k gitops/kind
kubectl --context kind-idea-board --namespace argocd get applications --watch
```

Wait for `local`, `ingress-controller`, `idea-board`, `backend` and `frontend` to each show `Synced` and `Healthy`. Check every Application: a healthy parent alone does not confirm that its children are ready.

The root waits for PostgreSQL before creating its child Applications. Backend sync runs migrations in a separate `PreSync` Job. A failed migration blocks backend deployment.

### Where the local settings live

| File | Purpose |
| --- | --- |
| `kind/root.yaml` | Root Application and its permissions; watches `master` |
| `local/values-kind.yaml` | Enables PostgreSQL and ingress; disables External Secrets |
| `applications/values-kind.yaml` | Backend and frontend child Applications |
| `kind/backend-values.yaml` | Backend image and Kubernetes Secret reference |
| `kind/frontend-values.yaml` | Frontend image and `localhost` ingress routes |

Local PostgreSQL uses development credentials from `local/values-kind.yaml`. The root creates a Kubernetes Secret directly. External Secrets, cloud SecretStores and their CRDs are disabled in this local profile. Cloud secret configuration remains in the cloud charts.

The database has a 1 GiB persistent volume. Data survives replacing its pod. Deleting the volume or kind cluster removes the data.

To release another image, update the tags in the backend/frontend values files and merge. Argo CD applies the change.

## 4. Open the app and Argo CD

Open [localhost:8081](http://localhost:8081).

For an existing cluster created without the port mapping, run this in a separate terminal:

```bash
kubectl --context kind-idea-board --namespace ingress-system port-forward service/ingress-controller 8081:80
```

To open Argo CD, leave this running in another terminal:

```bash
kubectl --context kind-idea-board --namespace argocd port-forward service/argocd-server 8080:443
```

Open [localhost:8080](https://localhost:8080). Argo CD uses a local self-signed certificate. Sign in as `admin` with the initial password:

```bash
kubectl --context kind-idea-board --namespace argocd get secret argocd-initial-admin-secret \
  -o jsonpath='{.data.password}' | base64 --decode
```

## 5. Test the app

With the app reachable through ingress:

```bash
IDEA_BOARD_BASE_URL=http://localhost:8081 npm --prefix apps/frontend run test:stack
IDEA_BOARD_BASE_URL=http://localhost:8081 LOAD_CYCLES=1000 LOAD_CONCURRENCY=25 \
  npm --prefix apps/frontend run test:load
```

To check staging, preview redeployment, cleanup, failed rollout and rollback:

```bash
export IMAGE_TAG=5ae00d82541190e313a06e14f39ddc94124455a8
export CHART_REVISION="$(git rev-parse HEAD)"
uv sync --project tools/deploy --locked --all-groups
uv run --project tools/deploy python tools/deploy/tests/check_kind.py \
  --context kind-idea-board --image-tag "$IMAGE_TAG" --revision "$CHART_REVISION" \
  --evidence-output /tmp/idea-board-failed-rollout.json
```

The chart revision must be pushed to the public repository so Argo CD can fetch it. The image tag above identifies published application images.

The check uses fixed AI-response fixtures and creates isolated test databases and namespaces. It refuses existing staging/test-preview environments and removes its own environments afterward. Run it before creating the persistent demo below. See the [recorded verification](kind/verification.md).

## 6. Keep staging and a preview running

Each environment has a parent Application with backend and frontend children:

```text
idea-board-staging                 idea-board-pr-123
├── idea-board-staging-backend      ├── idea-board-pr-123-backend
└── idea-board-staging-frontend     └── idea-board-pr-123-frontend
```

The deployment tool creates staging's database on the local PostgreSQL server. Preview `123` gets its own namespace, database and login on the same server. Staging must be healthy before creating a preview.

Using the image and chart variables from step 5, deploy with the recorded recommendation:

```bash
uv run --project tools/deploy python tools/deploy/deploy.py release \
  --cloud kind --environment staging \
  --image-tag "$IMAGE_TAG" --revision "$CHART_REVISION" \
  --recommendation gitops/kind/evidence/recommendation.json --context kind-idea-board

uv run --project tools/deploy python tools/deploy/deploy.py release \
  --cloud kind --environment preview --pr 123 \
  --image-tag "$IMAGE_TAG" --revision "$CHART_REVISION" \
  --recommendation gitops/kind/evidence/recommendation.json --context kind-idea-board
```

The tool updates the parent, waits for the backend, then updates the frontend. It checks both services and their HTTP responses before reporting a verified release.

With ingress reachable on port `8081`:

- Staging: [idea-board-staging.localhost:8081](http://idea-board-staging.localhost:8081)
- Preview: [idea-board-pr-123.localhost:8081](http://idea-board-pr-123.localhost:8081)

Browsers resolve `.localhost` names locally. For a command-line client that does not, use an explicit mapping:

```bash
curl --resolve idea-board-staging.localhost:8081:127.0.0.1 \
  http://idea-board-staging.localhost:8081/api/ideas
```

Preview `123` is a local example. Remove it when finished:

```bash
uv run --project tools/deploy python tools/deploy/deploy.py cleanup \
  --cloud kind --environment preview --pr 123 \
  --image-tag "$IMAGE_TAG" --revision "$CHART_REVISION" --context kind-idea-board
```

Cleanup removes the parent first, then its services, namespace and preview database. The [deployment tool guide](../tools/deploy/README.md) covers AI planning and rollback.

## Inspect or stop

```bash
kubectl --context kind-idea-board --namespace argocd get applications
kubectl --context kind-idea-board --namespace idea-board get pods,jobs,pvc,ingress
kubectl --context kind-idea-board --namespace idea-board logs deployment/backend
kubectl --context kind-idea-board --namespace idea-board logs job/backend-migrate
```

Successful migration Jobs are removed, so their logs are available while they run or after a failure. Stopping a port-forward closes its local address. The cluster keeps running.

To delete the cluster and its data:

```bash
kind delete cluster --name idea-board
```
