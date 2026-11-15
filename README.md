# Idea Board

Idea Board is a small web application where people can share, browse, and delete ideas. It uses React, FastAPI, and PostgreSQL. The surrounding platform builds and tests containers, provisions AWS or GCP infrastructure with Terraform, and deploys through Argo CD. An AI deployment skill helps choose resource settings and investigate failed releases.

The application stays deliberately small so the infrastructure and release process are easy to follow. This guide starts with a browser request, follows it through the application, and then explains how to run, test, and deploy the system.

## Contents

- [Overview and end-to-end design](#overview-and-end-to-end-design)
- [Application](#application)
- [Repository layout](#repository-layout)
- [Local development](#local-development)
- [Testing and load checks](#testing-and-load-checks)
- [Deployment](#deployment)
- [AI integration](#ai-integration)
- [Operations and troubleshooting](#operations-and-troubleshooting)
- [Cloud portability](#cloud-portability)
- [Verification status](#verification-status)

## Overview and end-to-end design

### A request through the application

The frontend uses **client-side rendering**. Nginx serves HTML, JavaScript, and CSS; React runs in the browser and builds the page. Once loaded, React makes separate HTTP requests to the API to read or change ideas. FastAPI returns JSON, and React updates the screen.

In local Compose development, requests follow this path:

```mermaid
sequenceDiagram
    participant Browser as Browser / React
    participant Web as Frontend Nginx
    participant API as FastAPI
    participant DB as PostgreSQL
    Browser->>Web: GET / and JavaScript/CSS assets
    Web-->>Browser: Static files
    Note over Browser: React renders the page in the browser
    Browser->>Web: GET /api/ideas?limit=50
    Web->>API: Forward /api request
    API->>DB: Read ideas
    DB-->>API: Rows
    API-->>Web: JSON array
    Web-->>Browser: JSON array
    Note over Browser: React displays the ideas
```

Both page and API requests originate in the browser and use the same public address, which avoids a separate browser API URL and CORS setup. Locally, Nginx forwards `/api/` requests to the backend through the Compose network.

Cloud configuration uses an Ingress to route `/api` and `/api/*` directly to the API Service and other paths to the frontend Service. The AWS Load Balancer Controller or GKE's built-in Ingress controller creates the public load balancer and registers backends. Terraform owns the cluster and required controller identity; Argo CD owns the routing manifests. See the [post-cluster ingress setup](infra/ingress/README.md). Live cloud verification of this routing is still pending.

### From source code to a running release

```mermaid
flowchart TD
    Code[Source commit] --> CI[GitHub Actions: app, container, Helm and Terraform checks]
    CI --> Images[GHCR: frontend and backend images tagged with commit SHA]
    Images --> Request[Choose tested commit and describe workload]
    Request --> AI[AI skill proposes resources and release plan]
    AI --> Validate[Validate output and render configuration]
    Validate --> Sizing[Terraform sizing proposal: review and apply separately]
    Validate --> Release[Deployment tool submits Argo Applications]
    Release --> Migration[Backend migration Job]
    Migration --> Backend[Backend rollout and health checks]
    Backend --> Frontend[Frontend rollout and health checks]
    Frontend --> Verify[HTTP and public endpoint checks]
    Verify --> Result[Verified release checkpoint and application URL]
    Release --> Evidence[Collect rollout evidence]
    Evidence --> Diagnosis[AI diagnosis and suggested next steps]
```

Infrastructure must exist before an application release. Terraform creates the network, Kubernetes cluster, and managed database. A routine release reuses them and deploys a tested image commit. AI-generated infrastructure sizing is reviewed separately; an application release does not automatically apply Terraform.

| Layer                              | Responsibility                                          | Why it is separate                                          |
| ---------------------------------- | ------------------------------------------------------- | ----------------------------------------------------------- |
| React and Nginx                    | Browser UI, static files, current API proxy             | Frontend can be built and released independently.           |
| FastAPI                            | Validation, HTTP API, database access                   | Application rules live behind one API.                      |
| PostgreSQL and Alembic             | Persistent data and versioned schema changes            | Database changes run before the backend starts.             |
| Docker and Compose                 | Reproducible images and local startup                   | Local development runs the complete stack with one command. |
| Terraform                          | Cloud networks, clusters, databases                     | Infrastructure changes have their own plan and state.       |
| Helm and Argo CD                   | Kubernetes manifests and application reconciliation     | Each service has its own chart and Application.             |
| GitHub Actions and deployment tool | Tests, image publishing, release ordering, verification | A release succeeds only after the requested version works.  |
| AI skill                           | Resource proposals and evidence-based diagnosis         | Helps operators decide; validated code controls execution.  |

## Application

### Frontend

The frontend uses React, TypeScript, and Vite. Vite builds static assets for the Nginx image and provides the development server when running on the host.

The UI loads ideas in pages of 50, newest first. Users can submit text, refresh the list, load older entries, and delete an idea after confirmation. Failed submissions preserve the draft, and failed reads offer a retry. Idea content is displayed as plain text.

React calls relative URLs such as `/api/ideas`. In development, Vite proxies those requests to the local backend. In the built container, Nginx forwards them to `BACKEND_UPSTREAM`, which defaults to `backend:8000`. No API address is embedded in the JavaScript build.

See the [frontend guide](apps/frontend/README.md) for UI behavior and build details.

### Backend and API

The backend uses FastAPI, SQLAlchemy, and psycopg. It validates requests, reads and writes PostgreSQL, and returns JSON. It does not render frontend pages.

| Method and endpoint                    | Behavior                                                                | Success response         |
| -------------------------------------- | ----------------------------------------------------------------------- | ------------------------ |
| `GET /api/ideas`                       | Return all ideas, newest ID first                                       | `200`, JSON array        |
| `GET /api/ideas?limit=50`              | Return up to 50 ideas; include a `Link` header when another page exists | `200`, JSON array        |
| `GET /api/ideas?limit=50&before_id=42` | Return the next page of ideas with IDs below 42                         | `200`, JSON array        |
| `POST /api/ideas`                      | Create an idea from `{"content":"..."}`                                 | `201`, created idea      |
| `DELETE /api/ideas/{idea_id}`          | Delete the specified idea                                               | `204`, empty body        |
| `GET /health`                          | Query the ideas table to check database access                          | `200`, `{"status":"ok"}` |

For example, with Compose running:

```bash
curl -i http://localhost:3000/api/ideas \
  -H 'Content-Type: application/json' \
  -d '{"content":"Make deployments easier to investigate"}'
```

The response is `201 Created`, with this shape:

```json
{
  "id": "42",
  "content": "Make deployments easier to investigate",
  "created_at": "2026-11-15T10:00:00Z"
}
```

IDs are decimal strings so the browser can preserve PostgreSQL bigint values. Timestamps are in UTC. Listing returns an array of these objects. Pagination uses an ID cursor so new submissions do not shift older pages; `limit` accepts 1–100, and `before_id` requires `limit`.

Content is trimmed and must contain 1–2,000 characters. Exact duplicate text is rejected after trimming; comparison is case-sensitive. Duplicate submissions return `409`, invalid input returns `422`, and deleting an absent idea returns `404`. Database unavailability returns `503` without exposing connection details.

Writes are not automatically retried: a lost response does not establish whether the database committed the request. The app currently permits anonymous creation and deletion; it has no user accounts or authorization layer.

Interactive API documentation is available at [localhost:8000/docs](http://localhost:8000/docs) when running locally. See the [backend guide](apps/backend/README.md) for the full validation and configuration contract.

### Database and migrations

PostgreSQL stores one application table:

| Column       | Type                         | Purpose                                                              |
| ------------ | ---------------------------- | -------------------------------------------------------------------- |
| `id`         | Generated bigint primary key | Identifies ideas and provides the pagination cursor.                 |
| `content`    | Text                         | Stores the idea; database constraints enforce length and uniqueness. |
| `created_at` | Timestamp with time zone     | Records creation time using the database clock.                      |

Alembic tracks schema versions. Migrations run as a **separate job before the backend starts**:

- Compose runs the `migrate` service and requires a successful exit before starting the backend.
- The backend Helm chart runs a migration Job before install/upgrade; Argo CD treats it as a `PreSync` hook. Failure blocks that backend sync.

The API never runs migrations. During startup it checks the database and required schema, then exits if either is unavailable. Once running, `/health` checks database access; Kubernetes readiness uses it to control traffic.

## Repository layout

```text
apps/
  frontend/                     React, Nginx, Dockerfile, frontend and HTTP tests
  backend/                      FastAPI, Alembic, Dockerfile, backend tests
docker-compose.yml              Frontend, backend, migration job, PostgreSQL
charts/
  idea-board-frontend/           Frontend Helm chart
  idea-board-backend/            Backend chart and migration hook
gitops/                         Argo CD installation and local Applications
infra/ingress/                   Post-cluster AWS controller setup and GKE setup notes
infra/terraform/
  aws/                          AWS root configuration and state backend
  gcp/                          GCP root configuration and state backend
  modules/{aws,gcp}/             Independent network, cluster, and psql modules
tools/deploy/                   Deployment, verification, diagnosis, rollback, tests
.agents/skills/deploy/           AI instructions and output schemas
.github/workflows/              CI, deployment, PR preview workflows
```

Tests live with the application, tool, or Terraform module they verify.

## Local development

### Start the complete stack

You need Git and a running Docker-compatible engine with Compose support. Host Python and Node installations are optional when running everything in containers.

```bash
git clone https://github.com/rohitraut3366/Idea-Board.git
cd Idea-Board
docker compose up --build --wait
```

Startup follows this order:

```text
PostgreSQL healthy → migration completes → backend healthy → frontend starts
```

Open [the web app](http://localhost:3000), submit an idea, refresh the page, and confirm it remains in the list. `docker compose ps --all` shows running services and the completed migration service; a successful migration exits with code 0.

| Component                                  | Local address           |
| ------------------------------------------ | ----------------------- |
| Web app, including proxied `/api` requests | `http://localhost:3000` |
| Direct API access and `/docs`              | `http://localhost:8000` |
| PostgreSQL                                 | `127.0.0.1:55432`       |

Compose supplies development credentials through process environment variables. Backend and migration processes both read `IDEA_BOARD_DATABASE_URL`; no `.env` file is required. PostgreSQL stores data in a named volume, so restarting containers preserves ideas.

### Logs, rebuilds, and shutdown

Run these commands from the repository root:

```bash
# Check service state, including the completed migration job.
docker compose ps --all

# Follow application logs, or inspect migration output.
docker compose logs -f frontend backend
docker compose logs migrate

# Rebuild and start services after changing application code.
docker compose up --build --wait

# Stop and remove containers; keep database data.
docker compose down
```

To reset the local database, the following commands **delete all Compose database data** and recreate the stack:

```bash
docker compose down --volumes
docker compose up --build --wait
```

### Develop with host processes

For frontend live reload, keep the Compose backend running. Install Node 24 and run in another terminal:

```bash
cd apps/frontend
npm ci
npm run dev
```

Open the address Vite prints. Its `/api` proxy reaches the backend at `127.0.0.1:8000`.

For backend live reload, install Python 3.12 and uv. From the repository root, stop the container processes that depend on the backend and keep PostgreSQL running:

```bash
docker compose stop frontend backend
docker compose up -d --wait postgres
cd apps/backend
uv sync --locked --all-extras --all-groups
export IDEA_BOARD_DATABASE_URL='postgresql+psycopg://idea_board:idea_board_local@127.0.0.1:55432/idea_board'
uv run alembic upgrade head
uv run uvicorn idea_board.server:create_app --factory --host 127.0.0.1 --port 8000 --reload
```

Use the Vite process above for the frontend. Apply migrations before starting the API. To return to container development, stop the host API process and run `docker compose up --build --wait` from the repository root.

## Testing and load checks

### Application checks

With Compose PostgreSQL running, execute backend checks from `apps/backend`:

```bash
uv sync --locked --all-extras --all-groups
uv run --all-extras --all-groups pytest
uv run --all-extras --all-groups mypy
uv run ruff check .
uv run ruff format --check .
```

Backend integration tests create a temporary database, apply real migrations, exercise the API, and remove that database. They cover persistence, pagination, concurrent duplicate writes, deletion, and database failures without truncating the development database.

Execute frontend checks from `apps/frontend`:

```bash
npm ci
npm test
npm run typecheck
npm run format:check
npm run build
```

Component tests use simulated API responses. With a disposable Compose stack running, run the following from the repository root to check built assets and real create/read/delete requests through Nginx:

```bash
npm --prefix apps/frontend run test:stack
```

This HTTP test writes test data. Browser-driven end-to-end UI testing remains pending.

### Load checks and capacity testing

With Compose running, start a repeatable concurrency check from the repository root:

```bash
LOAD_CYCLES=100 LOAD_CONCURRENCY=10 npm --prefix apps/frontend run test:load
```

Each cycle creates, reads, and deletes an idea. The runner reports request count, errors, elapsed time, throughput, p95 request latency, and cleanup failures. It deletes the IDs it receives, including after read failures, and fails for request errors or unsuccessful cleanup. `LOAD_MAX_P95_MS` can enforce an agreed latency target.

Set `IDEA_BOARD_BASE_URL` to target a port-forward or a cloud endpoint:

```bash
IDEA_BOARD_BASE_URL=https://YOUR_APPLICATION_HOST \
  LOAD_CYCLES=100 LOAD_CONCURRENCY=10 \
  npm --prefix apps/frontend run test:load
```

A local concurrency check confirms behavior under overlapping requests. To measure cloud capacity, run the generator outside the cluster, increase concurrency in steps, and collect pod CPU/memory, database CPU/connections, and saturation alongside latency and errors. Record the image commit, replica counts, worker/database sizes, and test parameters. A local Docker engine or port-forward can become the bottleneck, so its throughput is not a cloud capacity result.

### What CI checks

[CI](.github/workflows/ci.yml) runs application tests and static checks, builds both images, starts Compose, exercises full-stack HTTP requests and a small load check, and validates Helm install/upgrade and repeated migrations in kind. Terraform roots and modules have validation and provider-mock tests.

After those checks, CI publishes images and runs an Argo integration test. It exercises staging, preview persistence and cleanup, injects an image pull failure, and verifies rollback preserves schema/data while skipping migration hooks. The [deployment tool guide](tools/deploy/README.md) and [Terraform guide](infra/terraform/README.md#checks-without-cloud-accounts) contain their local check commands.

## Deployment

Cloud setup and application releases are separate operations. Complete the first three steps below once per target environment; routine application releases start at step 4.

### 1. Provision infrastructure with Terraform

Terraform has separate AWS and GCP roots. Each calls independent modules with readable provider-specific resources:

| Module    | AWS                                                      | GCP                                                                       |
| --------- | -------------------------------------------------------- | ------------------------------------------------------------------------- |
| `network` | VPC, subnets, routes, internet gateway, NAT              | VPC, subnet, pod/service ranges, Cloud NAT, private database connectivity |
| `cluster` | EKS, managed workers, IAM roles and administrator access | GKE, worker pool, node identity and Workload Identity                     |
| `psql`    | Private RDS PostgreSQL and managed credentials           | Private Cloud SQL PostgreSQL and Secret Manager credentials               |

The network supplies connectivity to the cluster and database. The database accepts application traffic over private networking. PostgreSQL is not exposed to the internet. Kubernetes API endpoints require cloud authentication and Kubernetes authorization; their current configuration permits public network reachability without a caller-IP allowlist.

Before provisioning, configure cloud credentials and create a remote state bucket separately. Use distinct stack names and state keys for staging and production. State tracks real resources and may contain credentials; restrict bucket access and enable encryption and versioning.

From the repository root, choose AWS:

```bash
cd infra/terraform/aws
# For GCP, use infra/terraform/gcp instead.
cp terraform.tfvars.example terraform.tfvars
cp backend.hcl.example backend.hcl
```

Edit both files with your region, zones, supported Kubernetes version, cloud identity, and state bucket. AWS uses an existing administrator role; GCP requires a billed project, Application Default Credentials, and `TF_VAR_database_password` supplied through the process environment. Use Terraform 1.17.x and the committed provider lock files.

Then run from the selected Terraform directory:

```bash
terraform init -backend-config=backend.hcl
terraform fmt -check -recursive
terraform validate
terraform plan -out=stack.tfplan
# Review the resources, access settings, and costs before applying.
terraform apply stack.tfplan
terraform output
```

A successful apply creates infrastructure; it does not deploy the app. Note the `cluster_name`, `database_host`, `database_port`, `database_name`, `database_username`, and `database_credential_secret_id` outputs for the deployment configuration below. The secret ID references stored credentials; it is not the password.

A real Terraform plan requires cloud credentials and account access. Provider-mock tests check configuration without creating resources, but cannot verify cloud permissions, quotas, or regional availability. See the [Terraform guide](infra/terraform/README.md) for state setup, all variables, capacity settings, and teardown.

### 2. Configure Kubernetes, Argo CD, and public routing

Connect to the new cluster using `aws eks update-kubeconfig` or `gcloud container clusters get-credentials`. Use explicit Kubernetes contexts so commands target the intended cluster.

Install the pinned Argo CD configuration from `gitops/argocd` into the `argocd` namespace. Argo CD renders the frontend and backend Helm charts as separate Applications. The deployment tool creates a namespace-scoped AppProject and cloud Applications, pins the charts/images to the selected source commit, and supplies Helm values. Database Secrets are provisioned separately from the Application manifests.

For local Kubernetes, the [GitOps guide](gitops/README.md) covers installation, existing kind Applications, and port-forwarding. Those local Applications use `gitops/kind` values and configured Git revisions; inspect them before applying. They are separate from the cloud Applications generated by the deployment tool.

#### Public routing on AWS and GCP

Use the [ingress setup guide](infra/ingress/README.md) after cluster creation. On AWS, a separate Terraform root provisions controller IAM and EKS Pod Identity; apply its generated Argo Application to install the controller. On GCP, the cluster enables the built-in HTTP load-balancing controller, so no extra installation is required.

```mermaid
flowchart LR
    Browser[Browser / React] -->|Page and asset requests| LB[Controller-managed public load balancer]
    Browser -->|/api/* requests| LB
    LB -->|Other paths| Front[Frontend Service and pods]
    LB -->|/api and /api/*| Back[API Service and pods]
    Back --> DB[Private PostgreSQL]
```

The frontend chart owns one Ingress with both routes. Backend and frontend Services remain ClusterIP. AWS uses an internet-facing ALB with pod IP targets. GKE uses container-native load balancing with network endpoint groups and explicit BackendConfig health checks. Cloud API traffic bypasses frontend Nginx; the proxy remains available for Compose and local kind.

Controllers own the cloud load-balancer resources, health checks, and registrations. Terraform does not manage individual load balancers or target groups. Staging, production, and each PR namespace use the same routing model, with one public load balancer per namespace. Public routing currently uses HTTP; DNS, certificates, and HTTPS need additional configuration.

### 3. Configure GitHub deployment access

The [Deploy workflow](.github/workflows/deploy.yml) uses short-lived cloud credentials through GitHub OIDC. Configure the trust relationship for this repository and its intended GitHub Environment:

- **AWS:** a deployment role with an EKS access entry, Kubernetes permissions, and permission to read the selected database credential secret.
- **GCP:** Workload Identity Federation and a deployment service account with cluster access and access to the selected Secret Manager secret.

These deployment identities and trust relationships are prerequisites; the current Terraform roots do not create GitHub OIDC setup. Cloud access keys are not needed in repository secrets.

Create the GitHub Environments you intend to deploy to: `aws-staging`, `aws-production`, `gcp-staging`, and `gcp-production`. Add production reviewers and deployment branch rules. Previews use their cloud's staging Environment.

| Environment variable                              | Value                                       |
| ------------------------------------------------- | ------------------------------------------- |
| `CLOUD_REGION`                                    | AWS region or GKE cluster location          |
| `CLUSTER_NAME`                                    | Terraform `cluster_name` output             |
| `DATABASE_HOST`, `DATABASE_PORT`, `DATABASE_NAME` | Corresponding Terraform outputs             |
| `DATABASE_USERNAME`                               | Terraform output; used by GCP               |
| `DATABASE_CREDENTIAL_SECRET_ID`                   | Terraform credential secret reference       |
| `AWS_ROLE_ARN`                                    | AWS deployment role ARN; AWS only           |
| `GCP_PROJECT_ID`                                  | GCP project ID; GCP only                    |
| `GCP_WORKLOAD_IDENTITY_PROVIDER`                  | Federation provider resource name; GCP only |
| `GCP_SERVICE_ACCOUNT`                             | Deployment service account email; GCP only  |

Add `OPENAI_API_KEY` as a repository Actions secret for the current AI runner. Its planning and diagnosis jobs run without cloud credentials. At release time, the deployment job retrieves the database password and supplies the connection URL to Kubernetes through stdin; it is not included in Application manifests or release artifacts.

### 4. Build, publish, and release an application version

CI publishes public images at:

```text
ghcr.io/rohitraut3366/idea-board-frontend:<full-commit-sha>
ghcr.io/rohitraut3366/idea-board-backend:<full-commit-sha>
```

Both images support `linux/amd64` and `linux/arm64`. Dockerfiles install locked dependencies before copying application code, so code changes can reuse dependency layers. Builds use package-download caches and GitHub Actions layer caching. Runtime stages contain the files needed to run each service.

Publishing follows successful checks on pushes to `master`, manual CI runs, and same-repository PRs. Fork PRs run checks but cannot publish or deploy previews. GitHub's built-in token authenticates image publishing.

To release:

1. Wait for CI, including image publishing, to succeed for the source commit. Copy its full SHA.
2. Run **Actions → Deploy**, select the cloud/environment, supply the SHA, and describe the workload. For example: `Low-traffic staging for a few reviewers; keep costs small`.
3. Review the generated recommendation and `release-plan` artifacts: rendered Applications, `plan.md`, and cloud staging/production `sizing.tfvars.json`. If infrastructure capacity needs changing, use the sizing file alongside existing stack inputs to review/apply Terraform separately. Configure Environment approval rules when a review gate is required.
4. The deployment tool creates the namespace and database Secret, checkpoints the attempt, and submits the backend Application. Its migration Job must succeed before the backend rollout.
5. Once the backend is Synced and Healthy with the requested image, values, Deployment generation, and replicas, the tool submits and verifies the frontend. It checks backend health and exercises full-stack HTTP requests through a port-forward.
6. For cloud releases, it waits for the Ingress hostname/IP and checks both the page and API there. Only then does it save the healthy checkpoint and publish the URL in the run summary and result artifact.

An old healthy Deployment cannot satisfy verification for a different release. If any required check fails, the release stays failed.

The equivalent GitHub CLI command is:

```bash
gh workflow run deploy.yml --ref master \
  -f cloud=aws -f environment=staging \
  -f image_tag=FULL_40_CHARACTER_COMMIT_SHA \
  -f request='Low-traffic staging for a few reviewers; keep costs small'
```

Choose `cloud=gcp` for GCP. Workflows must exist on the selected ref; automatic preview workflows must exist on the default branch. Cloud Applications are stored in Kubernetes and workflow artifacts; the tool does not commit generated environment configuration back to Git.

### 5. Staging, production, and PR previews

| Environment | Purpose                                  | Isolation                                                                                               |
| ----------- | ---------------------------------------- | ------------------------------------------------------------------------------------------------------- |
| Staging     | Verify changes before production         | Separate Terraform stack/state and application namespace from production                                |
| Production  | Run the stable application               | Its own infrastructure configuration, state, namespace, and GitHub Environment rules                    |
| PR preview  | Review one branch's frontend and backend | Per-PR namespace, Applications, database, login, and Secret; shares staging cluster and database server |

Once staging is healthy, set repository Actions variable `PREVIEW_CLOUD` to `aws` or `gcp`. Leave it unset to disable automatic previews.

For same-repository PRs, successful CI triggers the [preview workflow](.github/workflows/preview.yml). It checks that the PR is still open and the tested SHA is still its head. PR 42 receives namespace `idea-board-pr-42`, separate frontend/backend Applications, and database `idea_board_pr_42` with a dedicated login. Each preview gets its own Ingress and controller-managed public load balancer. No per-preview Terraform changes are needed.

The staging backend provisions preview databases from inside the private network. Its database identity must be able to create databases and roles. Redeployment preserves preview data and credentials. Closing the PR removes its Applications, namespace, database, and role. Ownership checks protect unrelated databases, and automated cleanup rejects production. If staging is unavailable during cleanup, restore it and retry.

Fork PRs never receive deployment credentials or previews. The privileged preview workflow runs default-branch tooling; application images and charts from same-repository PRs remain trusted developer code, so repository write access controls who can deploy them.

## AI integration

The [deployment skill](.agents/skills/deploy/SKILL.md) contains planning and diagnosis instructions, supported by JSON output schemas. The skill is independent of an AI vendor or runner. The current workflow uses the [Codex Action](https://developers.openai.com/codex/github-action/); another compatible runner can produce the same JSON files for the deployment tool.

### Planning a release

An operator describes the workload, such as `Staging for a few reviewers; keep resource use small`. The model proposes independent backend/frontend replicas, CPU requests, memory requests and limits, plus cloud worker/database sizing for staging or production. Each proposal includes reasons and an ordered release plan.

The Python tool validates the response before cloud authentication. It renders Helm values and assembles commands from trusted inputs. The model cannot change the cloud, namespace, image SHA, or chart revision, and its prose is never executed as shell code.

| Output                            | Use                              | Practical value                                                                       |
| --------------------------------- | -------------------------------- | ------------------------------------------------------------------------------------- |
| Application resource settings     | Helm values for each service     | Turns a workload description into reviewable configuration.                           |
| Terraform sizing variables        | Separate infrastructure proposal | Makes worker/database choices explicit without automatically resizing a shared stack. |
| Ordered plan and reasons          | Release artifact                 | Shows what will happen and why before deployment.                                     |
| Diagnosis with evidence citations | Post-deployment artifact         | Helps an operator investigate a failure from collected facts.                         |

Validation bounds values, checks memory limits cover requests, restricts previews to one small replica per service, and requires at least two replicas per service, multiple workers, and a standby database in production proposals. Machine types must belong to the selected cloud. These settings are starting points: replica counts alone do not guarantee placement or measured capacity.

Terraform generation reuses supported sizing inputs in the existing modules. It does not generate arbitrary resources, identities, or security policies. Previews share staging infrastructure and receive no Terraform sizing proposal.

### Diagnosing a rollout

The deployment tool collects bounded readiness, restart and exit facts; Job status; event reasons; recognized error signatures; and CPU/memory snapshots when Metrics Server is available. Raw logs, event messages, Secrets, and environment variables are excluded. Missing sources are recorded as evidence gaps.

A separate AI job returns an assessment, cited evidence, an explanation, and suggested next steps. For example, an unpublished image should produce image-pull evidence and an investigation or rollback recommendation. The model cannot override failed health checks, execute its suggestions, or initiate rollback. Collection and analysis also run for successful releases when evidence is available.

Deterministic fixtures test the contract and release mechanics without model credentials. A live call to the configured runner remains unverified after a transport failure; this is separate from the passing deployment-tool and Argo integration checks.

## Operations and troubleshooting

### Investigate a failure

Start with the workflow's failed step and deployment diagnostics artifact. For Kubernetes inspection, set an explicit context and namespace:

```bash
kubectl --context YOUR_CONTEXT --namespace YOUR_NAMESPACE get pods,jobs
kubectl --context YOUR_CONTEXT --namespace argocd get applications
kubectl --context YOUR_CONTEXT --namespace YOUR_NAMESPACE logs job/backend-migrate
```

| Symptom                                      | Check first                                                                                            |
| -------------------------------------------- | ------------------------------------------------------------------------------------------------------ |
| Compose backend does not start               | `docker compose logs migrate` and PostgreSQL health; migrations must complete first.                   |
| Host API cannot bind port 8000               | Stop the Compose backend before starting a host process.                                               |
| Migration Job fails                          | Job logs, database connectivity, credentials, and the migration change. Fix the cause before retrying. |
| Pod reports `ImagePullBackOff`               | Repository/tag, image publication, platform support, registry access, and package visibility.          |
| Argo cannot sync                             | Application conditions, chart revision, AppProject permissions, and migration status.                  |
| Pods are healthy but public checks fail      | Ingress controller, Ingress address, target health, routing, and security rules.                       |
| Preview cleanup fails                        | Staging backend availability, database administration permissions, and resource ownership.             |
| Cloud authentication fails before deployment | OIDC trust and Environment variables; rollout evidence may not exist yet.                              |

### Roll back application code

The deployment tool saves the last verified pair of Applications in an `idea-board-release` ConfigMap per namespace. A failed release does not replace it. A first release has no predecessor, and manually deployed environments acquire a checkpoint only after a successful tool-managed release.

To restore it, run Deploy with `operation=rollback`, the **failed** image SHA, the same target, and `schema_compatible=true`. Confirm first that the previous application supports the current database schema.

Rollback checks for changed Applications, mismatched attempts, and queued/running Argo operations before changing either service. It restores the verified sources and values, pauses automatic sync, and requests an explicit Argo apply sync that skips migration hooks. Verification waits for that specific operation, checks the rollout and HTTP behavior, then updates the checkpoint. The next regular release enables automatic sync again and runs migrations normally.

Rollback preserves database contents, schema, and credentials. Database downgrades are separate reviewed operations because they may lose data. Use backward-compatible migrations so the previous application can run against the newer schema. Inspect and terminate a stuck Argo sync before retrying rollback.

### Remove cloud infrastructure

Use the original credentials, variables, and state backend to review `terraform plan -destroy` before running `terraform destroy` in the selected root. First remove application resources and Ingress resources and wait for controller-managed load balancers to be deleted while their controller is available. Remove the AWS controller setup after that cleanup. Follow the [Terraform teardown instructions](infra/terraform/README.md) for database deletion protection, final snapshots, retained backups, and state storage. Destroying Kubernetes alone does not establish that every billable cloud resource has been removed.

## Cloud portability

Both clouds run the same images, HTTP API, PostgreSQL schema, migration command, Helm charts, and release verification. Cloud-specific resources stay in their Terraform roots and authentication adapters.

| Concern                | AWS                                  | GCP                          | Shared interface                                           |
| ---------------------- | ------------------------------------ | ---------------------------- | ---------------------------------------------------------- |
| Kubernetes             | EKS                                  | GKE                          | Kubernetes resources and Helm values                       |
| Database               | RDS PostgreSQL                       | Cloud SQL PostgreSQL         | PostgreSQL connection URL                                  |
| Infrastructure         | AWS modules                          | GCP modules                  | `network`, `cluster`, `psql` boundaries and common outputs |
| Deployment credentials | IAM role via GitHub OIDC             | Workload Identity Federation | Short-lived cloud authentication                           |
| Credential storage     | Secrets Manager                      | Secret Manager               | Kubernetes database Secret                                 |
| Current public routing | AWS Load Balancer Controller and ALB | GKE Ingress and pod NEGs     | Same-origin page and API access                            |

Selecting the cloud and its GitHub Environment changes the deployment target. Region, identity, network ranges, Kubernetes versions, and machine sizes remain explicit provider configuration. Ingress annotations and health configuration stay provider-specific while both expose the same-origin page and API routes.

A third provider would need its infrastructure modules, authentication/secret adapter, and public-routing configuration. Application code and the common release checks can remain the same. Moving an existing database between clouds requires a separate data migration; choosing another cloud does not move its data.

## Verification status

| Area                       | Verified                                                                                                               | Remaining                                                                                 |
| -------------------------- | ---------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------- |
| Application and containers | Backend/frontend checks, Compose HTTP tests, migrations, Helm checks                                                   | Browser-driven end-to-end UI suite                                                        |
| Argo release mechanics     | Kind staging and preview lifecycle, injected image failure, rollback without migration hooks, schema/data preservation | Cloud workflow identities and public routing verification                                 |
| AWS infrastructure         | Live provision, application pods and HTTP access through a port-forward, unchanged follow-up plan, teardown            | Current hosted deployment and public URL; live verification of controller-managed Ingress |
| GCP infrastructure         | Terraform validation and provider-mock tests                                                                           | Live plan/apply, application deployment, public URL                                       |
| AI integration             | Output validation, sizing generation, evidence filtering, rollback guards                                              | Successful live runner response                                                           |
| Load testing               | Repeatable local/CI concurrency checks                                                                                 | Measured cloud capacity under increasing load                                             |

No permanent AWS or GCP application URL is currently maintained. The cloud deployment workflow reports a working URL only after public page and API checks pass. Local tests establish application behavior and release mechanics; they cannot establish cloud permissions, managed-service compatibility, or public reachability.
