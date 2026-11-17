# Deployment tool

The tool turns validated AI recommendations into Helm values, a Terraform sizing proposal, and a release plan. It deploys the two services through Argo CD, gathers rollout evidence, and supports restoring the last verified application release.

## Plan a release locally

For setup, live AI prompts and runnable commands, follow [Plan and deploy with AI on kind](../../gitops/README.md#6-plan-and-deploy-with-ai). The runner must follow the deployment skill and return JSON matching its schema. The walkthrough uses Codex CLI; another compatible runner can provide the same JSON.

Review `release-plan/plan.md` and `release-plan/applications.json`. The plan includes individual service replicas, CPU and memory values, an ordered deployment explanation, and a release command built by Python. The model cannot change the cloud, namespace, image, or revision, or supply executable shell text. `render` prints only the Applications; `prepare` writes the review files. All commands validate the recommendation first.

For AWS/GCP staging or production, select `--cloud aws` or `--cloud gcp` when generating the prompt and preparing the release. `prepare` also writes separate `release-plan/terraform/cluster/sizing.tfvars.json` and `release-plan/terraform/applications/idea-board/sizing.tfvars.json` proposals for their Terraform projects. The files contain worker count/type and database tier/storage/standby configuration respectively. These values supplement your stack configuration. Use the Terragrunt plan commands in `plan.md`, replacing `YOUR_REGION` with your target region, with your own credentials, state backend, and stack variables. Review actual changes before applying, especially storage, region-specific sizes, and GCP node count (a multiple of your node-zone count). The application release does not apply infrastructure changes. Kind and PR previews have no sizing file.

## Deploy

For kind, first follow the [local bootstrap](../../gitops/README.md). Each local environment runs its own PostgreSQL Deployment and volume through the backend chart. The tool creates a random password and connection URL in that environment's Kubernetes Secret and reuses them on redeployment. It refuses an existing Secret pointing to a shared server; migrate that environment's data or recreate it explicitly before deploying. Staging uses `idea-board-staging`. The tool refuses to adopt a namespace without its ownership labels. Cloud child Applications create their namespace with those same labels. A cloud staging/production release checks that the existing root matches the requested cloud and environment before changing anything.

Use `release` with the same image, revision and recommendation as `prepare`, plus an explicit Kubernetes context. The [kind walkthrough](../../gitops/README.md#6-plan-and-deploy-with-ai) contains the release command and [preview example](../../gitops/README.md#7-create-a-preview).

On kind, each environment has a parent Application containing its backend and frontend Applications. The tool updates the parent with the new backend while keeping the serving frontend, then updates the frontend once the backend is ready. AWS and GCP staging/production releases update the existing `idea-board` root in the same order. The root owns the service Applications. Cloud previews have their own Applications.

The backend migration runs in its separate Job. Cloud staging/production creates the ExternalSecret first, then runs the migration as a Sync hook in wave -1. Bundled PostgreSQL also starts before migrations run as a Sync hook. The backend must be Synced and Healthy at the requested revision and image before the frontend is submitted. Both services must pass rollout and full-stack HTTP checks before the tool records the release as verified. Cloud runs additionally check the public page and API. External Secrets supplies cloud staging/production database credentials from the Terraform-generated backend values. Local and preview credentials are created by the deployment tool. Cloud access and Environment variables are described in the [cloud deployment guide](../../infra/cloud-deployment.md#3-configure-github-actions).

A preview uses `--environment preview --pr 123`. It gets its own PostgreSQL Deployment, volume and credentials in its namespace. Redeployment preserves the data and credentials. It needs no staging or production database access. The close-PR workflow calls `cleanup`; manual cleanup uses the same target arguments. Kind cleanup deletes the parent before its children so the parent cannot recreate them. Deleting the preview namespace removes its Secret and PostgreSQL volume. Cleanup rejects staging and production and checks namespace ownership.

Cloud previews use the cluster's default storage provisioner for their PostgreSQL volumes. EKS needs an installed EBS CSI driver and a default StorageClass; GKE uses its Persistent Disk provisioner. The AWS Terraform stack does not currently install the EBS CSI add-on.

## Diagnose a rollout

Every release attempt writes `deployment-diagnostics.json`. It records check outcome, pod readiness/restarts, migration Job counts, event reasons, recognized error signatures from bounded current/previous logs, and resource usage when available. Raw log lines, event messages, container environment, and Secrets stay out of the artifact. Missing APIs/logs are recorded as gaps. This is a snapshot for explaining a rollout, not continuous monitoring.

Follow [Explain a failed rollout with AI](../../gitops/README.md#9-explain-a-failed-rollout-with-ai) to get an explanation with one skill invocation. Use `deployment-diagnostics.json` to inspect your own release attempt.

In CI, `diagnosis.md` contains validated advice with references to collected evidence. Validation rejects a model response that declares a failed deterministic check healthy, invents evidence IDs, or requests rollback without a verified predecessor. Advice never executes commands. GitHub Actions runs diagnosis in a separate job after rollout, even if the deployment failed, so the model has no cloud credentials. Failures before the release tool starts have no rollout artifact.

## Roll back application code

Each namespace has an `idea-board-release` ConfigMap containing the last verified Application specifications and the current attempted release. It contains no database credentials. A first deployment has no predecessor. Failed releases do not replace the verified checkpoint.

Confirm that the preceding application version supports the **current** database schema, then supply the failed image/chart SHAs:

```bash
uv run --project tools/deploy python tools/deploy/deploy.py rollback \
  --cloud kind --environment staging \
  --image-tag "$IMAGE_TAG" --revision "$CHART_REVISION" \
  --context kind-idea-board --schema-compatible
```

Rollback restores both Argo sources and Helm values, pauses automatic sync, and requests an explicit Argo apply sync that skips hooks, including old migrations. It waits for that specific operation to succeed and verifies rollout and HTTP behavior before replacing the checkpoint. Database contents, schema, and credentials are not reverted. Automatic sync stays paused until the next regular release, which enables it again and runs migrations normally.

For kind and cloud staging/production, rollback also validates and pauses the owning root or parent, then restores its desired child sources. The root or parent and the restored children stay paused until the next release.

The tool checks both Applications before changing either. It refuses a mismatched failed SHA, an Application changed since the attempt, a missing predecessor, or an active Argo operation. Terminate a stuck sync in Argo CD and inspect its hooks before retrying. A partial rollback remains visible and can be retried after the underlying problem is resolved. GitHub Actions exposes the same operation as `operation=rollback` with `schema_compatible=true`; it uses the target's existing deployment Environment rules.

## Verification

Run the deployment tool checks:

```bash
uv run --project tools/deploy --locked ruff check tools/deploy
uv run --project tools/deploy --locked ruff format --check tools/deploy
uv run --project tools/deploy --locked mypy tools/deploy --check-untyped-defs --ignore-missing-imports
uv run --project tools/deploy --locked pytest tools/deploy/tests
```

Tests cover independent sizing, environment limits, Argo CD Application configuration, Terraform input mapping, isolated database credentials, evidence filtering, unsupported model advice, rollback state/drift checks, preview ownership/cleanup, and PR provenance.

The Terraform CI jobs also run `tests/check_terraform.py` for generated staging and production sizing against the cluster and application projects for both clouds using native provider mocks. This validates resource wiring without account credentials; it does not establish cloud permissions, quotas, or regional capacity.

CI runs the Kubernetes deployment checks with fixed recommendations, independently of model availability. A live AI runner invocation tests the skill separately. Hosted runner authentication, cloud federation, managed database permissions, and external routing still require checks in the target accounts.

## Public routing

Follow the [public routing setup](../../infra/ingress/README.md) before cloud releases. AWS uses the AWS Load Balancer Controller; GCP uses GKE's built-in Ingress controller. The tool generates provider-specific annotations, GCP BackendConfig resources, and an Ingress routing to both ClusterIP Services. Previews use the same model in their own namespaces; no Terraform updates or preconfigured target-group IDs are needed per preview.

The final public check reads `Ingress/frontend` in the release namespace and verifies both the page and API at its reported hostname/IP. Controllers must remain available during preview cleanup so deleting the Ingress also removes its cloud resources. Local kind uses Traefik ingress with a hostname for each environment; see the [kind guide](../../gitops/README.md).
