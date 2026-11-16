# Run Idea Board locally with kind and Argo CD

This walkthrough creates a Kubernetes cluster on your laptop, deploys the app, then uses AI to plan staging and preview releases.

The sequence is:

```text
Create kind → install Argo CD → deploy Idea Board → test the app
                                                    ↓
Build a version → ask AI for settings → review → release staging
                                                    ↓
                                  Preview → load test → AI diagnosis
```

## Before you start

Start Docker Desktop. Install kind 0.32.0 or newer, kubectl, Helm, Node.js 24, Python 3.12 and uv. The AI steps also need an authenticated Codex CLI.

For a new checkout, download the repository and enter it:

```bash
git clone https://github.com/rohitraut3366/Idea-Board.git
cd Idea-Board
```

If you already have the repository, open a terminal in its root: the directory containing `apps`, `charts` and `docker-compose.yml`.

Run the commands in order. Keep this terminal open: later steps reuse variables defined here. Where a step needs another terminal, leave the original one available for the next command.

## 1. Create the cluster

Kind runs Kubernetes inside Docker. This command creates a cluster named `idea-board`. The configuration file defines its node and maps local port `8081` to the app's ingress entry point.

```bash
kind create cluster --name idea-board --config gitops/kind/config.yaml
```

If that cluster already exists and was created with the current configuration, continue with the next command. Updating the configuration file does not upgrade an existing cluster.

Select the cluster once. The remaining `kubectl` commands use this selection. Kind stores its connection details in your kubeconfig, so it also appears in `kubectx`.

```bash
kubectl config use-context kind-idea-board
```

Check that the Kubernetes node is ready:

```bash
kubectl get nodes
```

Continue when its status is `Ready`.

## 2. Install Argo CD

Argo CD reads the deployment configuration from Git and keeps the cluster in sync with it.

Create its namespace:

```bash
kubectl create namespace argocd
```

If the namespace already exists, continue. Install the Argo CD version pinned in `gitops/argocd`. Server-side apply handles its large Kubernetes resource definitions.

```bash
kubectl apply --server-side -k gitops/argocd
```

Wait for the web server:

```bash
kubectl --namespace argocd rollout status deployment/argocd-server --timeout=5m
```

Wait for the component that reads the repository:

```bash
kubectl --namespace argocd rollout status deployment/argocd-repo-server --timeout=5m
```

Wait for the controller that manages Applications:

```bash
kubectl --namespace argocd rollout status statefulset/argocd-application-controller --timeout=5m
```

Continue when all three report a successful rollout.

## 3. Apply the root

The root is an Argo CD Application that declares the other Applications to deploy. This is the app-of-apps pattern:

```text
idea-board
├── ingress-controller → Traefik routes browser requests
├── backend → PostgreSQL, migration Job and FastAPI
└── frontend → React files served by Nginx
```

Helm renders the root and its permissions. The pipe sends those manifests to `kubectl apply`, which creates them in the cluster. `cloud=kind` selects the local app declarations. The root follows `master` and uses the image versions declared in the charts.

```bash
helm template idea-board infra/terraform/modules/argocd/bootstrap --namespace argocd \
  --set cloud=kind | kubectl apply -f -
```

Watch Argo CD create and deploy the children:

```bash
kubectl --namespace argocd get applications --watch
```

Wait until `idea-board`, `ingress-controller`, `backend` and `frontend` each show `Synced` and `Healthy`. Press Ctrl+C to stop watching; the applications keep running.

PostgreSQL starts first. A separate migration Job prepares its tables before FastAPI is deployed. The local chart creates the database Secret using development credentials. PostgreSQL stores data on a persistent volume.

The local settings are in:

| File | Purpose |
| --- | --- |
| [applications/values-kind.yaml](applications/values-kind.yaml) | Select the Applications for this cluster |
| [Backend values-kind.yaml](../charts/idea-board-backend/values-kind.yaml) | Enable local PostgreSQL and database credentials |
| [Frontend values-kind.yaml](../charts/idea-board-frontend/values-kind.yaml) | Configure the local ingress routes |

## 4. Open the app and Argo CD

Open [localhost:8081](http://localhost:8081). Submit an idea and refresh the page: the idea should still be there.

Browser requests travel through Traefik. Page requests go to the frontend; `/api` requests go to FastAPI, which reads and writes PostgreSQL.

If your existing kind cluster was created without the port mapping, expose ingress in another terminal and leave the command running:

```bash
kubectl --namespace ingress-system port-forward service/ingress-controller 8081:80
```

To see the Applications in Argo CD, use another terminal to expose its web server:

```bash
kubectl --namespace argocd port-forward service/argocd-server 8080:443
```

Leave it running and open [localhost:8080](https://localhost:8080). Accept the local self-signed certificate.

Retrieve the initial admin password in your main terminal. Keep the output out of recordings:

```bash
kubectl --namespace argocd get secret argocd-initial-admin-secret \
  -o jsonpath='{.data.password}' | base64 --decode
```

Sign in as `admin`. You should see the root and its three child Applications.

## 5. Test the app

Install the frontend project's dependencies, which are also used for the HTTP tests:

```bash
npm --prefix apps/frontend ci
```

Test the app at the ingress address. This checks the page and JavaScript files, then creates, lists and deletes test ideas through the API. It also checks pagination and invalid requests. It removes its test ideas afterward.

```bash
IDEA_BOARD_BASE_URL=http://localhost:8081 npm --prefix apps/frontend run test:stack
```

Continue when the test passes. GitHub Actions runs the separate automated bootstrap, preview and rollback checks on its own kind cluster.

## 6. Plan and deploy with AI

You now have a base app in namespace `idea-board`. Next, create a separate staging environment using settings proposed by AI. Staging gets frontend and backend deployments, its own PostgreSQL instance, credentials and persistent volume in `idea-board-staging`.

### What AI does

Your request describes the environment you want. The model recommends replica counts, CPU and memory and explains its choices. The deployment tool validates the recommendation, creates a plan and applies it after you review it.

```text
Your request + deployment skill
             ↓
      AI recommendation
             ↓
   Tool validates and writes a plan
             ↓
       You review the plan
             ↓
   Tool releases and checks the app
```

The [deployment skill](../.agents/skills/deploy/SKILL.md) supplies repository context, rules and the response format. `codex exec` makes the model call. The Python commands validate the settings and deploy the reviewed release.

### Build the version to deploy

Install the deployment tool's Python dependencies. In subsequent commands, `uv run --project tools/deploy` uses these dependencies to run the tool.

```bash
uv sync --project tools/deploy --locked --all-groups
```

Use a clean checkout of a pushed commit. Save its SHA as the chart revision so Argo CD can fetch those charts from Git:

```bash
export CHART_REVISION="$(git rev-parse HEAD)"
```

Use that same SHA as the version label for the two images you are about to build:

```bash
export IMAGE_TAG="$CHART_REVISION"
```

Build the backend image from the local backend source. `--load` saves the result in Docker so it can be copied into kind:

```bash
docker build --load -t "ghcr.io/rohitraut3366/idea-board-backend:$IMAGE_TAG" apps/backend
```

Build and save the frontend image the same way:

```bash
docker build --load -t "ghcr.io/rohitraut3366/idea-board-frontend:$IMAGE_TAG" apps/frontend
```

Load both images from Docker into kind. The charts use `IfNotPresent`, so Kubernetes can use these local images.

```bash
kind load docker-image --name idea-board \
  "ghcr.io/rohitraut3366/idea-board-backend:$IMAGE_TAG" \
  "ghcr.io/rohitraut3366/idea-board-frontend:$IMAGE_TAG"
```

### Ask AI for staging settings

**1. Ask AI for settings.** `$deploy` loads the deployment skill. The request selects kind staging and describes the workload. The schema defines the JSON settings that the deployment tool accepts; `--output-last-message` saves the model's answer for the next command. Codex also displays that answer in the terminal.

```bash
codex exec --sandbox read-only --ephemeral \
  --output-schema .agents/skills/deploy/output.schema.json \
  --output-last-message /tmp/idea-board-recommendation.json \
  '$deploy Recommend settings for cloud kind, environment staging. Local staging for a few reviewers. Use one backend replica and one frontend replica. Do not change the cluster.'
```

**2. Prepare the plan.** Validate the recommendation and generate the proposed Argo CD Applications in `release-plan/applications.json` and a readable plan in `release-plan/plan.md`. This writes local files; it does not change the cluster.

```bash
uv run --project tools/deploy python tools/deploy/deploy.py prepare \
  --cloud kind --environment staging \
  --image-tag "$IMAGE_TAG" --revision "$CHART_REVISION" \
  --recommendation /tmp/idea-board-recommendation.json
```

**3. Review the plan.** Check its target, resource settings and execution order before deploying:

```bash
cat release-plan/plan.md
```

**4. Release staging.** This changes the cluster: it creates staging's credentials and parent Application. The backend chart starts PostgreSQL and runs migrations before the backend becomes ready, then the tool releases the frontend and checks HTTP responses. The deployment tool requires `--context` to identify the cluster it will change.

```bash
uv run --project tools/deploy python tools/deploy/deploy.py release \
  --cloud kind --environment staging \
  --image-tag "$IMAGE_TAG" --revision "$CHART_REVISION" \
  --recommendation /tmp/idea-board-recommendation.json --context kind-idea-board
```

When the release succeeds, open [idea-board-staging.localhost:8081](http://idea-board-staging.localhost:8081). Argo CD should show `idea-board-staging` with backend and frontend children, all Synced and Healthy.

## 7. Create a preview

Use [PR #35](https://github.com/rohitraut3366/Idea-Board/pull/35), which gives the app a purple UI, to compare a proposed change with staging. Keep this PR open as the demo preview.

Preview `35` gets its own namespace, frontend, backend, PostgreSQL instance, persistent volume and generated credentials.

**1. Select the preview branch.** Run from the repository root in the same terminal. Fetch the branch and save its commit as the preview version. Separate preview variables preserve the staging version used later in this guide.

```bash
git fetch origin
git switch rohit-preview-purple-ui
git pull --ff-only

export PREVIEW_REVISION="$(git rev-parse HEAD)"
export PREVIEW_IMAGE_TAG="$PREVIEW_REVISION"
```

**2. Build and load the preview images.** Build both services from this branch. `--load` saves each image in Docker; `kind load` copies them into the local cluster.

```bash
docker build --load \
  -t "ghcr.io/rohitraut3366/idea-board-backend:$PREVIEW_IMAGE_TAG" apps/backend

docker build --load \
  -t "ghcr.io/rohitraut3366/idea-board-frontend:$PREVIEW_IMAGE_TAG" apps/frontend

kind load docker-image --name idea-board \
  "ghcr.io/rohitraut3366/idea-board-backend:$PREVIEW_IMAGE_TAG" \
  "ghcr.io/rohitraut3366/idea-board-frontend:$PREVIEW_IMAGE_TAG"
```

**3. Ask AI for preview settings.** `$deploy` loads the deployment skill. Codex displays its recommendation and saves the JSON settings for the release tool.

```bash
codex exec --sandbox read-only --ephemeral \
  --output-schema .agents/skills/deploy/output.schema.json \
  --output-last-message /tmp/idea-board-pr-35-recommendation.json \
  '$deploy Recommend settings for cloud kind, environment preview, PR 35. A small preview for reviewing the purple UI. Use one replica per service. Do not change the cluster.'
```

**4. Prepare its release plan.** Validate the recommendation and generate the preview Applications. This replaces the staging plan files in `release-plan/`.

```bash
uv run --project tools/deploy python tools/deploy/deploy.py prepare \
  --cloud kind --environment preview --pr 35 \
  --image-tag "$PREVIEW_IMAGE_TAG" --revision "$PREVIEW_REVISION" \
  --recommendation /tmp/idea-board-pr-35-recommendation.json
```

**5. Review the plan.** Confirm that the target is `idea-board-pr-35` and inspect its resource settings:

```bash
cat release-plan/plan.md
```

**6. Release the preview.** Create its credentials and parent Application, start its PostgreSQL instance and backend, deploy the frontend, and check the HTTP responses:

```bash
uv run --project tools/deploy python tools/deploy/deploy.py release \
  --cloud kind --environment preview --pr 35 \
  --image-tag "$PREVIEW_IMAGE_TAG" --revision "$PREVIEW_REVISION" \
  --recommendation /tmp/idea-board-pr-35-recommendation.json --context kind-idea-board
```

Open [idea-board-pr-35.localhost:8081](http://idea-board-pr-35.localhost:8081). Compare its purple UI with [staging](http://idea-board-staging.localhost:8081). Create an idea in the preview and check that staging's ideas are separate. Rerunning the release command preserves preview data.

The environments now look like this:

```text
idea-board                  Base app created by the root in step 3
idea-board-staging          Staging release planned with AI
├── ...-backend
└── ...-frontend
idea-board-pr-35            Purple UI from PR #35
├── ...-backend
└── ...-frontend
```

Leave the preview running for the demo. To deploy later changes from this PR, repeat this section to fetch, build and release the new version. The preview remains available while the cluster is running.

### Optional: remove the preview

Run this only when you want to delete the preview. It removes its parent and child Applications, namespace, credentials and PostgreSQL volume:

```bash
uv run --project tools/deploy python tools/deploy/deploy.py cleanup \
  --cloud kind --environment preview --pr 35 \
  --image-tag "$PREVIEW_IMAGE_TAG" --revision "$PREVIEW_REVISION" --context kind-idea-board
```

## 8. Test performance and scaling

Measure staging with one backend replica, then repeat the same workload with two.

In another terminal, expose staging's frontend on port `3002`. Leave this running during the measurements:

```bash
kubectl --namespace idea-board-staging port-forward service/frontend 3002:80
```

In your main terminal, check the current replica counts:

```bash
kubectl --namespace idea-board-staging get deployments
```

Run 1,000 cycles with up to 25 active at once. Each cycle creates an idea, lists ideas and deletes its test idea. The result reports requests per second, p95 response time and failures.

```bash
IDEA_BOARD_BASE_URL=http://localhost:3002 LOAD_CYCLES=1000 LOAD_CONCURRENCY=25 \
  npm --prefix apps/frontend run test:load
```

Repeat with `LOAD_CONCURRENCY=10` and `50`. `LOAD_CYCLES` controls the total work; concurrency controls how much happens in parallel. Set `LOAD_MAX_P95_MS` to enforce a response-time limit.

Create a copy of the staging recommendation with two backend replicas. This changes a local JSON file:

```bash
uv run --project tools/deploy python - <<'PYTHON'
import json
from pathlib import Path

settings = json.loads(Path('/tmp/idea-board-recommendation.json').read_text())
settings['backend']['replicas'] = 2
settings['reason'] = 'Compare local performance with two backend replicas.'
Path('/tmp/idea-board-two-replicas.json').write_text(json.dumps(settings, indent=2))
PYTHON
```

Release those settings to staging and wait for the deployment checks to finish:

```bash
uv run --project tools/deploy python tools/deploy/deploy.py release \
  --cloud kind --environment staging \
  --image-tag "$IMAGE_TAG" --revision "$CHART_REVISION" \
  --recommendation /tmp/idea-board-two-replicas.json --context kind-idea-board
```

Repeat the same load commands at the same concurrency values. Compare throughput, response times and failures. If the port-forward stopped during the release, restart it first. These results describe this local machine and workload.

Restore the original staging settings after the comparison:

```bash
uv run --project tools/deploy python tools/deploy/deploy.py release \
  --cloud kind --environment staging \
  --image-tag "$IMAGE_TAG" --revision "$CHART_REVISION" \
  --recommendation /tmp/idea-board-recommendation.json --context kind-idea-board
```

Stop the staging port-forward with Ctrl+C when you finish.

## 9. Explain a failed rollout with AI

This second AI feature explains a failure using collected deployment evidence. The example uses a recorded attempt where an unpublished frontend image failed to start. The previous release was restored during that earlier test.

For a failure from your own release, use its `deployment-diagnostics.json` instead of the recorded evidence path below.

Run this from the repository root. `$deploy` selects the deployment skill in `.agents/skills/deploy/`. Codex reads the recorded evidence and prints an explanation of the failure, the evidence supporting it, and suggested next steps. The single quotes keep `$deploy` as a skill mention rather than a shell variable.

```bash
codex exec --sandbox read-only --ephemeral \
  '$deploy Diagnose the rollout using gitops/kind/evidence/failed-rollout.json. Explain the failure and recommend the next steps. Do not change the cluster.'
```

This command analyzes the recorded attempt. GitHub Actions uses schema-validated JSON and saves its diagnosis as workflow artifacts.

Diagnosis provides advice. To restore an application release, follow the separate [rollback procedure](../tools/deploy/README.md#roll-back-application-code), including its database compatibility check.

## Inspect or stop

To check deployment status, list the Applications:

```bash
kubectl --namespace argocd get applications
```

To inspect the base app's containers, migration Jobs, storage and routes:

```bash
kubectl --namespace idea-board get pods,jobs,pvc,ingress
```

To read recent backend logs:

```bash
kubectl --namespace idea-board logs deployment/backend --tail=100
```

For staging or preview inspection, use that environment's namespace. Successful migration Jobs are removed; their logs are available while running or after failure.

Stopping a port-forward closes its local address. The cluster keeps running. When you are finished with the demo, this command deletes the cluster and its database volumes:

```bash
kind delete cluster --name idea-board
```
