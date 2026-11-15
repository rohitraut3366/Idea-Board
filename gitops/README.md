# Run Idea Board in kind

This runs PostgreSQL, the frontend, and the backend in a local Kubernetes cluster. Argo CD deploys the app from Git. Its cluster services root installs External Secrets Operator.

Docker, kind, kubectl, Helm, Python, uv, and Node.js are needed. Run the commands from the repository root.

## 1. Create the cluster

If `kind-idea-board` already exists, keep it and continue to step 2.

```bash
kind create cluster --name idea-board \
  --image kindest/node:v1.33.1@sha256:050072256b9a903bd914c0b2866828150cb229cea0efe5892e2b644d5dd3b34f
kubectl --context kind-idea-board get nodes
```

## 2. Start PostgreSQL

```bash
kubectl --context kind-idea-board --namespace idea-board apply -f gitops/kind/postgres.yaml
kubectl --context kind-idea-board --namespace idea-board rollout status deployment/postgres --timeout=3m
```

The manifest creates the namespace, local database credentials, and a 1 GiB persistent volume claim. The data survives replacing the PostgreSQL pod. Deleting the volume or kind cluster removes it.

## 3. Install Argo CD and shared services

```bash
kubectl --context kind-idea-board apply -f - <<'YAML'
apiVersion: v1
kind: Namespace
metadata:
  name: argocd
YAML
kubectl --context kind-idea-board apply --server-side -k gitops/argocd
kubectl --context kind-idea-board --namespace argocd rollout status deployment/argocd-server --timeout=5m
kubectl --context kind-idea-board --namespace argocd rollout status deployment/argocd-repo-server --timeout=5m
kubectl --context kind-idea-board --namespace argocd rollout status statefulset/argocd-application-controller --timeout=5m
python3 gitops/tests/check_core_services.py --context kind-idea-board --revision master
```

The last command installs the root Application and waits for it and External Secrets Operator to become Synced and Healthy. The operator is installed; connecting it to cloud credentials is separate from this local setup.

## 4. Deploy the app

```bash
kubectl --context kind-idea-board apply -k gitops/kind
kubectl --context kind-idea-board --namespace argocd wait application/backend application/frontend \
  --for=jsonpath='{.status.sync.status}'=Synced --timeout=5m
kubectl --context kind-idea-board --namespace argocd wait application/backend application/frontend \
  --for=jsonpath='{.status.health.status}'=Healthy --timeout=5m
kubectl --context kind-idea-board --namespace idea-board get pods
```

The two Applications watch `master` and use published GHCR images. Backend sync runs migrations in a separate `PreSync` Job. A failed migration blocks the release.

To release a new image, update the tag in `kind/backend-values.yaml` or `kind/frontend-values.yaml` and merge the change. Argo CD applies it.

## 5. Open the app

Run each port-forward in its own terminal and leave it running:

```bash
kubectl --context kind-idea-board --namespace idea-board port-forward service/frontend 3001:80
```

```bash
kubectl --context kind-idea-board --namespace argocd port-forward service/argocd-server 8080:443
```

- App: [localhost:3001](http://localhost:3001)
- Argo CD: [localhost:8080](https://localhost:8080), with its local self-signed certificate.

Argo CD's initial username is `admin`. Read its password locally:

```bash
kubectl --context kind-idea-board --namespace argocd get secret argocd-initial-admin-secret \
  -o jsonpath='{.data.password}' | base64 --decode
```

## 6. Verify the deployment

With the app port-forward running:

```bash
IDEA_BOARD_BASE_URL=http://127.0.0.1:3001 npm --prefix apps/frontend run test:stack
IDEA_BOARD_BASE_URL=http://127.0.0.1:3001 LOAD_CYCLES=1000 LOAD_CONCURRENCY=25 \
  npm --prefix apps/frontend run test:load
```

For staging, preview redeployment, cleanup, failure detection, and rollback checks:

```bash
uv sync --project tools/deploy --locked --all-groups
uv run --project tools/deploy python tools/deploy/tests/check_kind.py \
  --context kind-idea-board \
  --image-tag 5ae00d82541190e313a06e14f39ddc94124455a8 \
  --revision 5ae00d82541190e313a06e14f39ddc94124455a8 \
  --evidence-output /tmp/idea-board-failed-rollout.json
```

Run this check before creating the persistent staging demo below. It uses fixed AI-response fixtures. It creates its own staging and preview databases, deploys both services through Argo CD, redeploys the preview, and removes it. It then introduces a bad frontend image and verifies recovery to the last healthy release while preserving the database schema and data. It removes its test resources afterward. It refuses to run if the staging or test-preview namespace already exists.

See [the deployment tool](../tools/deploy/README.md) for a persistent staging or preview release and [the verification results](kind/verification.md) for the recorded run.

## 7. Keep staging and a preview running

The isolated check above removes its test environments. To keep demo environments visible in Argo CD, create a staging database once:

```bash
kubectl --context kind-idea-board --namespace idea-board exec deployment/postgres -- \
  psql -U idea_board -d idea_board -v ON_ERROR_STOP=1 -c 'CREATE DATABASE idea_board_staging_demo'
```

If that database already exists from an earlier demo, keep it and continue.

Use the recorded AI recommendation to deploy staging:

```bash
export IMAGE_TAG=5ae00d82541190e313a06e14f39ddc94124455a8
export CHART_REVISION="$IMAGE_TAG"
export IDEA_BOARD_DATABASE_URL='postgresql+psycopg://idea_board:idea_board_local@postgres.idea-board.svc.cluster.local:5432/idea_board_staging_demo'

uv run --project tools/deploy python tools/deploy/deploy.py release \
  --cloud kind --environment staging \
  --image-tag "$IMAGE_TAG" --revision "$CHART_REVISION" \
  --recommendation gitops/kind/evidence/recommendation.json --context kind-idea-board
```

Create sample preview `123`. It receives a separate namespace, database, and database login on the same PostgreSQL server:

```bash
uv run --project tools/deploy python tools/deploy/deploy.py release \
  --cloud kind --environment preview --pr 123 \
  --image-tag "$IMAGE_TAG" --revision "$CHART_REVISION" \
  --recommendation gitops/kind/evidence/recommendation.json --context kind-idea-board
```

Run these port-forwards in separate terminals:

```bash
kubectl --context kind-idea-board --namespace idea-board-staging port-forward service/frontend 3002:80
kubectl --context kind-idea-board --namespace idea-board-pr-123 port-forward service/frontend 3003:80
```

Staging is at [localhost:3002](http://localhost:3002); the sample preview is at [localhost:3003](http://localhost:3003). Preview `123` is a local example, not a deployment triggered by a GitHub PR.

Remove the sample preview through the deployment tool when finished:

```bash
uv run --project tools/deploy python tools/deploy/deploy.py cleanup \
  --cloud kind --environment preview --pr 123 \
  --image-tag "$IMAGE_TAG" --revision "$CHART_REVISION" --context kind-idea-board
```

## Inspect or stop

```bash
kubectl --context kind-idea-board --namespace argocd get applications
kubectl --context kind-idea-board --namespace idea-board get pods,jobs,pvc
kubectl --context kind-idea-board --namespace idea-board logs deployment/backend
kubectl --context kind-idea-board --namespace idea-board logs job/backend-migrate
```

Successful migration Jobs are removed, so their logs are available only while they run or after a failure.

Stopping a port-forward closes that local address. Rerun it if its pod is replaced during deployment. The cluster keeps running. To delete the cluster and its data:

```bash
kind delete cluster --name idea-board
```
