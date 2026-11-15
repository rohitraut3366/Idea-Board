# Idea Board

A web app for sharing ideas, built with React, FastAPI, and PostgreSQL. Submit an idea, browse recent entries, load older ones, or delete an entry with confirmation.

Source: [rohitraut3366/Idea-Board](https://github.com/rohitraut3366/Idea-Board).

## Architecture

```text
Browser → Nginx / React → FastAPI → PostgreSQL
                             ↑
                    separate migration Job

GitHub Actions → tests → GHCR images tagged with a commit SHA
       ↓
AI deployment skill → release plan + Helm values + Terraform sizing
                                   ↓
                            Argo CD → Kubernetes
                                   ↓
                        rollout evidence → AI diagnosis
```

The frontend serves static assets and proxies `/api` to the backend, so the browser uses one origin. FastAPI owns validation and database requests. PostgreSQL persists ideas and enforces duplicate rejection under concurrent writes.

The frontend and backend have separate Docker images and Helm charts. A separate migration Job runs before the backend release; a failed migration blocks the release. The API checks its database and schema during startup and exits if they are unavailable. It never runs migrations itself.

Compose runs PostgreSQL locally. Cloud deployments use private RDS or Cloud SQL instances. Argo CD manages application resources; Terraform owns networking, Kubernetes, and the managed database. This keeps a routine app release separate from infrastructure changes.

## Run locally

1. Install Git and a Docker-compatible engine with Compose support.
2. Clone the repository and enter it:

```bash
git clone https://github.com/rohitraut3366/Idea-Board.git
cd Idea-Board
```

3. Build and start the stack:

```bash
docker compose up --build --wait
```

4. Open [Idea Board](http://localhost:3000). API documentation is available at [localhost:8000/docs](http://localhost:8000/docs).

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

## Kubernetes

Separate Helm charts deploy the [backend](charts/idea-board-backend/README.md) and [web app](charts/idea-board-frontend/README.md). The backend chart runs migrations as a separate Job before install and upgrade, using an existing PostgreSQL database and Secret. The frontend chart connects to the backend Service.

[Argo CD setup](gitops/README.md) connects the two charts to Git, with separate Applications, migration hooks, and Git-based rollback.

## Container images

GitHub Actions publishes `ghcr.io/rohitraut3366/idea-board-backend` and `ghcr.io/rohitraut3366/idea-board-frontend` after backend, frontend, Compose, and Helm checks pass. Each image supports `linux/amd64` and `linux/arm64` and is tagged with the full source commit SHA.

Publishing runs after successful checks on pushes to `master`, manual CI runs, and PRs from branches in this repository. Fork PRs run checks but cannot publish or deploy previews. All CI jobs use the same source commit. The job uses GitHub's built-in token; no registry password is stored in the repository.

Update the image repository and commit tag in `gitops/kind/*-values.yaml` to deploy a published version through Argo CD. Both GHCR packages must be public for the local cluster to pull without credentials.

## Cloud infrastructure

[Terraform](infra/terraform/README.md) provisions networking, Kubernetes, and managed PostgreSQL on AWS or GCP through separate `network`, `cluster`, and `psql` modules. The guide covers configuration, state, credentials, capacity, and validation. AWS deployment, application checks through Argo CD, and teardown have passed in Sydney. GCP has schema validation and mocked tests; a live deployment is still pending.

## Deploy through GitHub Actions

The [Deploy workflow](.github/workflows/deploy.yml) deploys an already tested image commit. It leaves infrastructure provisioning as an explicit Terraform operation. The same workflow handles AWS and GCP; authentication and frontend load-balancer settings vary by provider.

### Configure a cloud environment

1. Follow the [Terraform guide](infra/terraform/README.md) to create a state bucket, configure the chosen root, and review/apply a plan. Use separate state keys and stack names for staging and production. The disposable AWS state bucket used during verification was deleted; create a new one before another apply.
2. Connect to the cluster with `aws eks update-kubeconfig` or `gcloud container clusters get-credentials`. Install the pinned Argo CD configuration from `gitops/argocd` into its `argocd` namespace, using an explicit context as shown in the [GitOps guide](gitops/README.md). The existing `gitops/kind` Applications belong to the local cluster; the deployment tool creates separate cloud Applications.
3. On AWS, install the AWS Load Balancer Controller with its required IAM permissions before releasing the frontend. The cloud frontend uses an internet-facing NLB with IP targets. GKE uses its built-in `LoadBalancer` Service integration. These controllers and their cloud permissions are prerequisites; the application charts do not install them.
4. Configure GitHub OIDC trust for this repository and the intended GitHub Environment. AWS needs a deployment role with an EKS access entry and permission to read the selected database secret. GCP needs a Workload Identity Federation provider and service account with cluster access and permission to read the selected Secret Manager secret. Keep trust restricted to this repository and environment. Do not store cloud access keys in GitHub.
5. Create GitHub Environments named `aws-staging`, `aws-production`, `gcp-staging`, and `gcp-production` for the targets you use. Configure required reviewers and deployment branch rules for production. Add the variables below to each Environment.
6. Add `OPENAI_API_KEY` as a repository Actions secret for the Codex action. The model runs in its own job without cloud credentials. Local Codex execution can use the operator's existing CLI sign-in; do not copy that sign-in file into a public repository or its workflows.

| GitHub Environment variable | Source |
| --- | --- |
| `CLOUD_REGION` | Terraform region |
| `CLUSTER_NAME` | Terraform `cluster_name` output |
| `DATABASE_HOST` | Terraform `database_host` output |
| `DATABASE_PORT` | Terraform `database_port` output |
| `DATABASE_NAME` | Terraform `database_name` output |
| `DATABASE_USERNAME` | Terraform `database_username` output; used by GCP |
| `DATABASE_CREDENTIAL_SECRET_ID` | Terraform `database_credential_secret_id` output |
| `AWS_ROLE_ARN` | AWS GitHub OIDC deployment role; AWS only |
| `GCP_PROJECT_ID` | GCP project; GCP only |
| `GCP_WORKLOAD_IDENTITY_PROVIDER` | GitHub federation provider resource name; GCP only |
| `GCP_SERVICE_ACCOUNT` | Deployment service account email; GCP only |

The credential secret reference is configuration, not the password. The runner fetches the password at release time and passes the database URL to Kubernetes through stdin. Previews share the staging cloud account, cluster, and database server. Their tables and credentials are separate.

### Run a release

1. Run CI on the source branch and wait for every job, including image publication, to succeed. Copy the full source commit SHA from the run.
2. Open **Actions → Deploy → Run workflow**, select the cloud and environment, paste the image SHA, and describe the intended workload. For example: `Staging for a few reviewers; keep resource use small`.
3. The AI runner proposes independent service resources, cloud sizing, and an ordered release plan. The plan job validates the response and uploads the recommendation, rendered Applications, `plan.md`, and (for cloud staging/production) `sizing.tfvars.json`. Review these before approving the deployment Environment. Infrastructure sizing is a proposal: use the generated file with your existing Terraform inputs and state to review a real plan and apply any needed capacity changes separately. The release job only deploys the application.
4. The tool creates the target namespace and database Secret, then submits separate backend and frontend Applications to Argo CD. It pins both charts and images to the selected source commit. Secrets stay outside the Application manifests and CI artifacts.
5. The backend must be healthy before the workflow submits the frontend release. The workflow waits for the requested Argo source and values to be Synced and Healthy, then checks that the running Deployment generation, images, and available replicas match. An old healthy release cannot satisfy this check. It verifies backend health and runs the frontend's full-stack HTTP test through a port-forward.
6. For cloud releases, it waits for a public frontend address and checks the page and API at that address. Only then does it publish the working URL in the run summary and `deployment-result` artifact.

Using GitHub CLI instead of the UI:

```bash
# Replace the SHA with the source commit from a successful image-publishing CI run.
gh workflow run deploy.yml --ref master \
  -f cloud=aws -f environment=staging \
  -f image_tag=FULL_40_CHARACTER_COMMIT_SHA \
  -f request='Low-traffic staging for a few reviewers'
```

Use `cloud=gcp` to target GCP. Workflows must be present on the selected branch; automatic preview events require them on the repository's default branch.

If a release fails, its job stays failed. A separate AI analysis job analyzes the collected evidence and saves a diagnosis with cited observations and suggested next steps. It cannot mark a failed health check healthy or execute its advice. Failures before the tool starts, such as cloud authentication errors, have no rollout evidence and need inspection in the failed job.

To restore the preceding verified release, run Deploy with `operation=rollback`, the **failed** image SHA, the same cloud/environment/PR, and `schema_compatible=true`. Confirm first that the preceding application code supports the current database schema. The tool checks the release checkpoint and current Applications, restores both Argo sources, skips migration hooks through selective sync, and reruns rollout and HTTP checks. It refuses rollback if another release changed the Applications, no previous verified release exists, or Argo still has a running sync; terminate a stuck sync in Argo CD and inspect its hooks before retrying. It does not reverse database changes or restore credentials.

The cloud workflow records generated Applications in its artifacts and Kubernetes; it does not commit environment changes back to Git. Existing local Applications continue to follow their configured Git branch.

### PR previews

Set the repository Actions variable `PREVIEW_CLOUD` to `aws` or `gcp` after staging is healthy. Leave it unset to keep automatic previews disabled. Preview operations use the selected cloud's staging GitHub Environment.

For an open PR from this repository, successful CI publishes its images and triggers [PR previews](.github/workflows/preview.yml). The workflow checks that the PR is still open and the successful commit is still its current head. Each PR gets:

- Namespace `idea-board-pr-<number>` with its own frontend and backend Applications.
- Database `idea_board_pr_<number>` and a dedicated login on the staging database server.
- Its own Kubernetes database Secret and public frontend Service.

The staging backend executes database administration inside the cluster, where the private server is reachable. This requires the staging database identity to create databases and roles. A preview redeploy keeps its database and password. Closing the PR removes its Applications, namespace, database, and role; production cleanup is rejected by the tool. Database and role ownership markers prevent cleanup from removing an unrelated database with a matching name. A healthy staging backend is required for provisioning and cleanup; retry cleanup after restoring staging if it was unavailable.

Fork PRs never receive deployment credentials or previews. The privileged preview workflow checks out the default branch and reads PR metadata; it never executes PR scripts. The application containers and Helm chart changes deployed from same-repository PRs are still trusted developer code, so restrict who can push those branches.

## AI integration

The [deployment skill](.agents/skills/deploy/SKILL.md) defines instructions for planning a release from a workload description and diagnosing rollout evidence. The instructions and JSON schemas are independent of the AI runner. A compatible agent can produce the recommendation and diagnosis files consumed by the Python deployment tool. The model runs in separate jobs without cloud credentials.

The current GitHub Actions workflow uses the official [Codex Action](https://developers.openai.com/codex/github-action/) with `OPENAI_API_KEY`; the local examples use Codex CLI. Using another runner requires changing those invocations while preserving the prompt inputs and JSON output contracts. The deployment logic and validation stay the same.

| Capability | What gets produced | How it is used |
| --- | --- | --- |
| Release planning | Ordered steps with reasons and a command assembled from validated inputs | Operators can review the exact target and execution order before deploying |
| Application sizing | Independent replicas, CPU requests, memory requests, and limits for each service | Converted to Helm values in the two Argo Applications |
| Infrastructure configuration | Cloud-specific worker count/type, database tier/storage, and standby setting | Written as Terraform JSON variables against the existing modules; reviewed and applied separately |
| Rollout diagnosis | Assessment, evidence IDs, explanation, and suggested next steps | Saved as a validated run artifact, including on failed deployments |
| Controlled rollback | A recommendation when evidence supports reverting the release | An operator explicitly restores the previous verified Argo sources after checking schema compatibility |

For example, a request for inexpensive reviewer access can produce one small backend and frontend with a single-zone database. A request to remain available during a node failure should produce additional application replicas, multiple workers, and a standby database, with the cost tradeoff explained. The recommendations are starting points: replica counts do not guarantee node placement or measured capacity. Run the load test against the proposed setup and use the results to adjust sizing.

The model chooses actual settings rather than selecting a fixed profile. JSON Schema and Python checks bound each value, reject additional fields, require memory limits to cover requests, limit previews to one small replica per service, and require at least two replicas per service plus multiple workers and a standby database for production proposals. AWS/GCP machine names must belong to the selected cloud. Trusted workflow inputs own the namespace, image, revision, and cloud. Model text never becomes executable shell code. The [deployment tool](tools/deploy/README.md) writes the release command from those validated inputs and enforces backend-before-frontend deployment.

Terraform generation deliberately stops at supported sizing inputs. It reuses the maintained network, cluster, and PostgreSQL modules; it does not invent resource blocks, credentials, or security settings. A real Terraform plan still needs the account, region, existing stack variables, and state. The pipeline does not silently resize a shared cluster or database during an application release. PR previews share staging infrastructure and receive no Terraform sizing file.

The diagnosis receives bounded pod readiness/restarts/exit reasons, Job status, event reason counts, recognized error signatures from recent/current and previous container logs, and CPU/memory snapshots when Metrics Server is available. Raw logs, event messages, environment variables, and Secrets are excluded. Missing sources appear as evidence gaps. These are deployment observations, not a historical monitoring system. The response must cite collected evidence, and it cannot override the deterministic rollout or HTTP checks. Suggested next steps are never executed. Rollback uses a per-namespace checkpoint saved by the deployment tool after a verified release; existing manually deployed environments have no checkpoint until their first successful tool-managed release.

CI tests the configuration contract, generated Helm values, generated Terraform sizing with provider mocks, evidence filtering, and rollback guards. Its kind integration check exercises staging, preview persistence and cleanup, then injects an image pull failure and restores the preceding Argo release. Explicit fixtures keep those checks repeatable without requiring model credentials. A live AI runner check and local kind verification are separate from cloud OIDC, managed database permissions, and public load balancer verification. No active cloud deployment or permanent public URL is maintained by these tests.

## Cloud-agnostic approach

The application uses HTTP, PostgreSQL, and Kubernetes resources rather than cloud-specific application APIs. Both clouds run the same published images, migration command, Helm charts, and deployment checks.

| Concern | Shared contract | AWS | GCP |
| --- | --- | --- | --- |
| Infrastructure | `network`, `cluster`, `psql` modules | VPC, EKS, RDS | VPC, GKE, Cloud SQL |
| Configuration | Cluster/database output names | AWS root variables | GCP root variables |
| CI | Same app, Compose, Helm, and Terraform checks | Mock AWS provider | Mock Google provider |
| Deployment identity | Short-lived GitHub OIDC credentials | Assumed IAM role | Workload Identity Federation |
| Database secret | Kubernetes `IDEA_BOARD_DATABASE_URL` | Secrets Manager | Secret Manager |
| Public access | Frontend `LoadBalancer` Service | AWS NLB controller | GKE load balancer integration |

Choose the cloud and its GitHub Environment to switch deployment targets. Provider-specific region, identity, network ranges, Kubernetes versions, and machine types remain explicit configuration. The Terraform roots expose the same database and cluster outputs, so the release logic does not need a separate implementation per cloud.

The roots deliberately use native provider resources. EKS and GKE do not have identical lifecycle or network behavior, and worker sizes are not interchangeable. Adding a third cloud means adding its three infrastructure modules, authentication/credential adapter, and frontend exposure settings while retaining the application charts and verification flow. Moving a live database between clouds requires a separate data migration; selecting another provider does not move existing data.

## Load testing and verification

With Compose running, run the repeatable concurrency check:

```bash
LOAD_CYCLES=100 LOAD_CONCURRENCY=10 npm --prefix apps/frontend run test:load
```

Use `IDEA_BOARD_BASE_URL` to test a port-forward or cloud URL. Set `LOAD_MAX_P95_MS` when the environment has an agreed request-latency target. The test reports request count, errors, elapsed time, throughput, and p95 request latency. It creates uniquely named ideas and deletes the IDs it receives, including after read failures. It exits unsuccessfully for request errors, failed cleanup, or an exceeded latency target.

CI runs a small concurrency check and, after image publication, exercises staging, preview redeployment/cleanup, image failure detection, and rollback through Argo CD in kind. For a capacity test, run the load generator outside the cluster, increase concurrency in steps, and record pod CPU/memory, database CPU/connections, and saturation alongside latency and errors. Keep the image commit, worker/database sizes, replica counts, and test parameters with the results. A port-forward or a local Docker engine can become the bottleneck; local throughput is not a cloud capacity result.

| Area | Verification |
| --- | --- |
| Compose and local kind | Full-stack HTTP checks passed; both local Argo Applications reached Synced and Healthy |
| AWS infrastructure and app | Applied in Sydney; pods and HTTP checks passed through a port-forward; second Terraform plan had no changes; stack and retained state storage were deleted afterward |
| GCP Terraform | Schema validation and mocked tests passed; live plan/apply pending |
| AI and cloud release workflows | Helpers and local rollout/rollback verified; live runner check hit transport errors before returning JSON; hosted model calls and cloud OIDC still need verification |
| Public application URLs | No AWS or GCP application is currently hosted; URLs are produced only after a successful public reachability check |

The local Argo release and rollback check used published image commit `34e9b27` and chart revision `f60da49`. CI is configured to repeat the flow against the source commit it publishes. A local Compose load run completed 100 cycles (300 requests) at concurrency 10 with no request or cleanup errors; p95 request latency was 37.64 ms. These numbers describe one run on a local machine.

Two working cloud URLs require two running cloud deployments. Local testing covers application behavior and the release mechanics available locally; it cannot establish cloud permissions, managed-service compatibility, or public routing.
