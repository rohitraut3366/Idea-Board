# Run Idea Board in kind

Argo CD reads the deployment configuration from Git and keeps the cluster in sync. You install Argo CD and apply one root Application. That root creates the Applications below it:

```text
idea-board
├── ingress-controller → Traefik
├── backend → PostgreSQL child chart, migration Job and FastAPI
└── frontend → React, Nginx and the Ingress routes
```

The browser loads the web app at `localhost:8081`. Requests to `/api` reach the backend through Traefik. PostgreSQL is reachable inside the cluster.

Docker, kind, kubectl, Helm, Python 3.12, uv and Node.js 24 are needed. The live AI examples use an authenticated Codex CLI; another runner can return JSON matching the same skill schemas. Run commands from the repository root.

Follow the steps in order: deploy the base app, test it over HTTP, then try live AI, previews and load tests.

## Prepare the tools and release

```bash
npm --prefix apps/frontend ci
uv sync --project tools/deploy --locked --all-groups
export CHART_REVISION="$(git rev-parse HEAD)"
export IMAGE_TAG="$CHART_REVISION"

docker build -t "ghcr.io/rohitraut3366/idea-board-backend:$IMAGE_TAG" apps/backend
docker build -t "ghcr.io/rohitraut3366/idea-board-frontend:$IMAGE_TAG" apps/frontend
```

Build from a clean checkout of a pushed commit. `CHART_REVISION` is that commit's SHA: Argo CD fetches the charts from Git. `IMAGE_TAG` gives both locally built images the same version. These variables are used by the deployment checks and AI examples below; keep using the same terminal.

## 1. Create the cluster

If `kind-idea-board` already exists, select it with `kubectl config use-context kind-idea-board`, then continue to step 2.

```bash
kind create cluster --name idea-board --config gitops/kind/config.yaml
kubectl config use-context kind-idea-board
kubectl get nodes
```

The kind configuration maps local port `8081` to Traefik's NodePort.

Load the images built above into the cluster, including when reusing an existing cluster:

```bash
kind load docker-image --name idea-board \
  "ghcr.io/rohitraut3366/idea-board-backend:$IMAGE_TAG" \
  "ghcr.io/rohitraut3366/idea-board-frontend:$IMAGE_TAG"
```

The charts use `IfNotPresent`, so Kubernetes can use these images directly from the kind node.

## 2. Install Argo CD

```bash
kubectl create namespace argocd
kubectl apply --server-side -k gitops/argocd
kubectl --namespace argocd rollout status deployment/argocd-server --timeout=5m
kubectl --namespace argocd rollout status deployment/argocd-repo-server --timeout=5m
kubectl --namespace argocd rollout status statefulset/argocd-application-controller --timeout=5m
```

If the namespace already exists, continue with the apply command.

## 3. Apply the root

```bash
helm template idea-board infra/terraform/modules/argocd/bootstrap --namespace argocd \
  --set cloud=kind | kubectl apply -f -
kubectl --namespace argocd get applications --watch
```

Wait for `idea-board`, `ingress-controller`, `backend` and `frontend` to each show `Synced` and `Healthy`. Check every Application: a healthy parent alone does not confirm that its children are ready.

The backend chart starts its PostgreSQL child chart, runs the migration Job, then deploys the backend. A failed migration blocks backend deployment.

### Where the local settings live

| File                                             | Purpose                                                          |
| ------------------------------------------------ | ---------------------------------------------------------------- |
| `../infra/terraform/modules/argocd/bootstrap/`   | Root Application and its permissions                             |
| `applications/values-kind.yaml`                  | Enables ingress, backend and frontend; disables External Secrets |
| `../charts/idea-board-backend/values-kind.yaml`  | Enables PostgreSQL with local credentials                        |
| `../charts/idea-board-frontend/values-kind.yaml` | `localhost` ingress routes                                       |

Local PostgreSQL uses development credentials from the backend chart's `values-kind.yaml`. The backend chart creates the Kubernetes database Secret. External Secrets, cloud SecretStores and their CRDs are disabled in this local profile. Cloud secret configuration remains in the cloud charts.

The database has a 1 GiB persistent volume. Data survives replacing its pod. Deleting the volume or kind cluster removes the data.

Each chart keeps its shared image defaults in `values.yaml` and its local overrides in `values-kind.yaml`. To release another image locally, set `applications.<service>.source.helm.valuesObject.image.tag` in `applications/values-kind.yaml` for each service and merge. Argo CD applies the updated values.

## 4. Open the app and Argo CD

Open [localhost:8081](http://localhost:8081).

For an existing cluster created without the port mapping, run this in a separate terminal:

```bash
kubectl --namespace ingress-system port-forward service/ingress-controller 8081:80
```

To open Argo CD, leave this running in another terminal:

```bash
kubectl --namespace argocd port-forward service/argocd-server 8080:443
```

Open [localhost:8080](https://localhost:8080). Argo CD uses a local self-signed certificate. Sign in as `admin` with the initial password:

```bash
kubectl --namespace argocd get secret argocd-initial-admin-secret \
  -o jsonpath='{.data.password}' | base64 --decode
```

## 5. Test the app

From the repository root, check the page and API through ingress:

```bash
IDEA_BOARD_BASE_URL=http://localhost:8081 npm --prefix apps/frontend run test:stack
```

GitHub Actions runs the automated bootstrap, cluster-service, preview and rollback checks on its own kind cluster.

## 6. Plan and deploy with AI

Staging gets its own PostgreSQL instance and volume in `idea-board-staging`. The release tool generates and retains its credentials. Ask for a small local staging environment:

```bash
uv run --project tools/deploy python tools/deploy/deploy.py prompt \
  --cloud kind --environment staging \
  --image-tag "$IMAGE_TAG" --revision "$CHART_REVISION" \
  --request 'Local staging for a few reviewers. Use one backend replica and one frontend replica.' \
  >/tmp/idea-board-prompt.md

codex exec --sandbox read-only --ephemeral \
  --output-schema .agents/skills/deploy/output.schema.json \
  --output-last-message /tmp/idea-board-recommendation.json \
  - </tmp/idea-board-prompt.md

uv run --project tools/deploy python tools/deploy/deploy.py prepare \
  --cloud kind --environment staging \
  --image-tag "$IMAGE_TAG" --revision "$CHART_REVISION" \
  --recommendation /tmp/idea-board-recommendation.json
```

The prompt includes the [deployment skill](../.agents/skills/deploy/SKILL.md). AI proposes replicas, CPU and memory. Python validates the response and generates the deployment commands.

The skill permits a fixed list of read-only `kubectl` commands to inspect settings, capacity, rollout status, resource descriptions, ConfigMaps, and bounded container logs. This local walkthrough uses `kind-idea-board`; AWS/GCP inspection requires an existing context explicitly supplied by the trusted caller. The runner must already have credentials and API access. The AI must not log in, change kubeconfig, configure permissions, or read Kubernetes Secrets. If access or metrics are unavailable, it states the gap and uses the supplied information. These are model instructions; Kubernetes RBAC controls actual permissions. Deployment changes stay with the deployment tool.

Review the recommendation and plan:

```bash
cat /tmp/idea-board-recommendation.json
cat release-plan/plan.md
```

Then deploy the reviewed settings:

```bash
uv run --project tools/deploy python tools/deploy/deploy.py release \
  --cloud kind --environment staging \
  --image-tag "$IMAGE_TAG" --revision "$CHART_REVISION" \
  --recommendation /tmp/idea-board-recommendation.json --context kind-idea-board
```

The tool creates staging's database credentials and parent Application. Its backend chart starts PostgreSQL and runs migrations before the backend becomes ready, then the tool releases the frontend. It checks HTTP responses before recording the release as healthy.

Open [idea-board-staging.localhost:8081](http://idea-board-staging.localhost:8081). For command-line clients that do not resolve `.localhost` names, leave this port-forward running in another terminal:

```bash
kubectl --namespace idea-board-staging \
  port-forward service/frontend 3002:80
```

Staging is then also available at [localhost:3002](http://localhost:3002).

## 7. Create a preview

Preview `123` gets a parent Application, frontend, backend, namespace, PostgreSQL instance, persistent volume and credentials. Its backend chart deploys a PostgreSQL instance and volume in the preview namespace. It uses neither staging nor production database credentials.

```bash
uv run --project tools/deploy python tools/deploy/deploy.py prompt \
  --cloud kind --environment preview --pr 123 \
  --image-tag "$IMAGE_TAG" --revision "$CHART_REVISION" \
  --request 'A small disposable preview for reviewing this change.' \
  >/tmp/idea-board-preview-prompt.md

codex exec --sandbox read-only --ephemeral \
  --output-schema .agents/skills/deploy/output.schema.json \
  --output-last-message /tmp/idea-board-preview-recommendation.json \
  - </tmp/idea-board-preview-prompt.md

uv run --project tools/deploy python tools/deploy/deploy.py prepare \
  --cloud kind --environment preview --pr 123 \
  --image-tag "$IMAGE_TAG" --revision "$CHART_REVISION" \
  --recommendation /tmp/idea-board-preview-recommendation.json
```

Review the preview recommendation and `release-plan/plan.md`, then deploy:

```bash
uv run --project tools/deploy python tools/deploy/deploy.py release \
  --cloud kind --environment preview --pr 123 \
  --image-tag "$IMAGE_TAG" --revision "$CHART_REVISION" \
  --recommendation /tmp/idea-board-preview-recommendation.json --context kind-idea-board
```

Open [idea-board-pr-123.localhost:8081](http://idea-board-pr-123.localhost:8081). Create an idea and rerun the release command to check that preview data survives redeployment.

Argo CD shows both environment parents:

```text
idea-board-staging                 idea-board-pr-123
├── idea-board-staging-backend      ├── idea-board-pr-123-backend
└── idea-board-staging-frontend     └── idea-board-pr-123-frontend
```

Remove the preview when finished:

```bash
uv run --project tools/deploy python tools/deploy/deploy.py cleanup \
  --cloud kind --environment preview --pr 123 \
  --image-tag "$IMAGE_TAG" --revision "$CHART_REVISION" --context kind-idea-board
```

This removes the preview's parent, services, namespace, database credentials and PostgreSQL volume.

## 8. Test performance and scaling

Use the staging port-forward from step 6. Check the running replica count and run a baseline load test:

```bash
kubectl --namespace idea-board-staging get deployments
IDEA_BOARD_BASE_URL=http://localhost:3002 LOAD_CYCLES=1000 LOAD_CONCURRENCY=25 \
  npm --prefix apps/frontend run test:load
```

Each cycle creates an idea, lists ideas and deletes its test idea. Record requests per second, p95 response time and errors. Repeat with `LOAD_CONCURRENCY=10` and `50` to increase parallelism. Set `LOAD_MAX_P95_MS` to enforce a response-time limit.

To compare two backend replicas, copy the reviewed staging settings and change the replica count:

```bash
uv run --project tools/deploy python - <<'PYTHON'
import json
from pathlib import Path

settings = json.loads(Path('/tmp/idea-board-recommendation.json').read_text())
settings['backend']['replicas'] = 2
settings['reason'] = 'Compare local performance with two backend replicas.'
Path('/tmp/idea-board-two-replicas.json').write_text(json.dumps(settings, indent=2))
PYTHON

uv run --project tools/deploy python tools/deploy/deploy.py release \
  --cloud kind --environment staging \
  --image-tag "$IMAGE_TAG" --revision "$CHART_REVISION" \
  --recommendation /tmp/idea-board-two-replicas.json --context kind-idea-board
```

Rerun the same load commands and compare results at matching concurrency. Releasing `/tmp/idea-board-recommendation.json` again restores the original sizing. These measurements describe your local machine's capacity.

## 9. Explain a failed rollout with AI

Use the recorded evidence from an earlier failed frontend rollout to ask AI what went wrong. This example makes a live model call about that captured failure; your current deployment stays unchanged:

```bash
uv run --project tools/deploy python tools/deploy/analyze.py prompt \
  --evidence gitops/kind/evidence/failed-rollout.json >/tmp/idea-board-diagnosis-prompt.md

codex exec --sandbox read-only --ephemeral \
  --output-schema .agents/skills/deploy/diagnosis.schema.json \
  --output-last-message /tmp/idea-board-diagnosis.json \
  - </tmp/idea-board-diagnosis-prompt.md

uv run --project tools/deploy python tools/deploy/analyze.py report \
  --evidence gitops/kind/evidence/failed-rollout.json \
  --diagnosis /tmp/idea-board-diagnosis.json

cat diagnosis.md
```

The report links the explanation to collected evidence. AI provides advice; the deployment checks and rollback command control the actual release. For a failure during your own staging release, use `deployment-diagnostics.json` from that attempt. See the [rollback procedure](../tools/deploy/README.md#roll-back-application-code) before restoring a previous release.

## Inspect or stop

```bash
kubectl --namespace argocd get applications
kubectl --namespace idea-board get pods,jobs,pvc,ingress
kubectl --namespace idea-board logs deployment/backend
kubectl --namespace idea-board logs -l app.kubernetes.io/component=migrate --all-containers=true
```

Successful migration Jobs are removed, so their logs are available while they run or after a failure. Stopping a port-forward closes its local address. The cluster keeps running.

To delete the cluster and its data:

```bash
kind delete cluster --name idea-board
```
