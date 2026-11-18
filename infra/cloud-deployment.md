# Cloud deployment

This guide covers AWS and GCP infrastructure, cluster access, GitHub Actions, releases, and cleanup. For the local demo, use the [kind walkthrough](../gitops/README.md).

Cloud configuration has Terraform validation and provider-mock coverage. Live deployment of these cloud projects, public routing, and cloud secret access remain unverified. There are no current hosted application URLs.

## Contents

- [Cloud-agnostic approach](#how-aws-and-gcp-use-the-same-app)
- [Create the cloud resources](#1-create-the-cloud-resources)
- [Connect to the cluster and check public routing](#2-connect-to-the-cluster-and-check-public-routing)
- [Configure GitHub Actions](#3-configure-github-actions)
- [Release the application](#4-release-the-application)
- [Environments and previews](#environments-and-previews)
- [Remove the cloud setup](#remove-the-cloud-setup)

## How AWS and GCP use the same app

Both clouds use the same application images, PostgreSQL schema, Helm charts, and release checks. Provider-specific networking, Kubernetes, database, identity, and ingress settings live in their infrastructure modules and deployment adapters.

Choose the cloud and its GitHub Environment to select the target. Adding another provider requires infrastructure modules and authentication, secret, and ingress adapters.

Deployment has two stages:

1. **Set up a place to run the app:** create the cloud network, Kubernetes cluster, database, and deployment access.
2. **Release an app version:** build its containers and tell the cluster to run them.

Follow steps 1–3 to set up an environment. Use step 4 whenever you want to release an app version.

## 1. Create the cloud resources

Terraform defines the resources. Terragrunt supplies their settings, state locations, and dependency order. Each cloud has four projects:

```text
infra/terraform/
├── state.hcl                         # Shared S3 state bucket and its region
├── root.hcl                          # Shared settings, state, and execution rules
├── aws/staging/
│   ├── environment.hcl               # Stack name
│   └── ap-southeast-2/
│       ├── region.hcl                # Region and availability zones
│       ├── networking/terragrunt.hcl
│       ├── cluster/terragrunt.hcl
│       ├── cluster-core-services/terragrunt.hcl
│       └── applications/idea-board/terragrunt.hcl
├── gcp/staging/                      # Same project layout for GCP
└── modules/                          # Reusable Terraform resources
```

Every project's `terragrunt.hcl` lists its required inputs and intentional overrides. Shared names, regions, zones, and GCP project selection are read through the exposed root include. Optional settings use defaults from the project's `variables.tf` unless overridden. AWS resolves cluster administrator access from your logged-in IAM identity. GCP uses `GOOGLE_CLOUD_PROJECT` or the project selected in gcloud. Database credentials are generated and stored in the cloud secret manager.

Before deploying:

1. Install Terraform 1.17.x, Terragrunt 1.2.2, kubectl, GitHub CLI, and your cloud CLI.
2. Sign in to AWS for infrastructure and state access. For GCP, also configure Application Default Credentials in a billed project.
3. Check `infra/terraform/state.hcl` points to your existing S3 state bucket. Both clouds use this bucket; project paths determine separate state keys.
4. Sign in to GitHub CLI and export its token for Terraform to publish shared-service values:

   ```bash
   export GITHUB_TOKEN="$(gh auth token)"
   ```

For AWS, select your authenticated profile and deploy:

```bash
export AWS_PROFILE=idea-board
cd infra/terraform/aws/staging/ap-southeast-2
terragrunt run --all apply
```

For GCP, run the same Terragrunt command from `infra/terraform/gcp/staging/australia-southeast1`. GCP deployments also use AWS credentials for the shared S3 state bucket.

Terragrunt initializes each project and applies them in dependency order:

```text
networking → cluster → cluster-core-services → applications/idea-board
```

A fresh stack needs its dependencies created before their consumers can be planned. For an existing stack, preview all changes with `terragrunt run --all plan`. To review and apply one project, run these commands from its directory:

```bash
terragrunt run -- plan -out=project.tfplan
terragrunt run -- apply project.tfplan
terragrunt run -- output
```

The cluster project provides `cluster_name`. The application project provides the database connection details and secret reference used in step 3. The [Terraform guide](terraform/README.md) covers settings, state, existing deployments, and teardown.

## 2. Connect to the cluster and check public routing

**Argo CD** runs inside the cluster. It reads the app's configuration from Git and makes the running services match it. Each service has a **Helm chart**, a template describing what Kubernetes should run.

The `cluster-core-services` project installs Argo CD and waits for it to be ready. On AWS it also installs the AWS Load Balancer Controller and its IAM permissions. GKE's HTTP load-balancing controller is enabled by the `cluster` project.

Terraform also creates a root Argo CD Application called `idea-board`. Its cloud values file selects which child Applications run. This is the **app-of-apps** pattern:

```text
Terraform → Argo CD → idea-board
                         ├── External Secrets Operator
                         ├── backend
                         └── frontend
```

Each `gitops/applications/values-kind.yaml`, `values-aws.yaml` and `values-gcp.yaml` file declares its own services. The default `values.yaml` contains shared settings and an empty applications map. Each service has its own chart under `charts/`. Both cloud profiles enable External Secrets, backend and frontend. Application children run in the cluster’s environment namespace, such as `idea-board-staging`. Terraform stores the connection URL in the cloud secret manager and publishes its reference, External Secrets copies the URL into the Kubernetes database Secret, and the release workflow updates the root with the selected images and sizing. The External Secrets umbrella chart wraps the upstream chart with our defaults.

External Secrets reads these files from its chart directory, in order. Later files override earlier ones:

```text
values.yaml
values/<cloud>/values.yaml
values/<cloud>/<cluster-name>/values.yaml
values/<cloud>/<cluster-name>/values-terraform.yaml
```

Provider and cluster files are optional. Argo CD ignores missing files and picks them up when they appear on the watched Git branch.

The External Secrets module creates the operator's cloud identity and secret-read permissions automatically: IRSA on AWS, Workload Identity on GCP. It writes the service-account annotation to `values-terraform.yaml` on `master`. Argo CD loads that file when rendering the operator chart. Keep `gitops_revision = "master"` to receive these updates.

The [GitOps Applications guide](../gitops/applications/README.md) explains application selection and chart overrides.

Connect `kubectl`, the Kubernetes command-line tool, to the cluster. Use its name from the previous step:

```bash
# AWS
aws eks update-kubeconfig --name YOUR_CLUSTER --region YOUR_REGION

# GCP
gcloud container clusters get-credentials YOUR_CLUSTER \
  --region YOUR_REGION --project YOUR_PROJECT
```

Check the Applications, then wait for External Secrets Operator to be ready:

```bash
kubectl --context YOUR_CONTEXT --namespace argocd get applications
kubectl --context YOUR_CONTEXT --namespace argocd wait application/external-secrets \
  --for=jsonpath='{.status.sync.status}'=Synced --timeout=10m
kubectl --context YOUR_CONTEXT --namespace argocd wait application/external-secrets \
  --for=jsonpath='{.status.health.status}'=Healthy --timeout=10m
```

When the app is released, its Ingress tells the controller to create a public load balancer and route browser requests to the frontend or API. The [ingress guide](ingress/README.md) explains the routes, health checks, and cleanup.

## 3. Configure GitHub Actions

**GitHub Actions** runs the deployment workflow. Give it access to the cloud through **OIDC**, which lets a workflow obtain temporary cloud credentials:

- **AWS:** a deployment role with EKS access and Kubernetes deployment permissions.
- **GCP:** Workload Identity Federation and a service account with cluster deployment access.

A **GitHub Environment** groups the settings and approval rules for a deployment target. Create the environments you will use: `aws-staging`, `aws-production`, `gcp-staging`, and `gcp-production`. Add reviewers to production environments.

Set these Environment variables:

| Variable                         | Value                            |
| -------------------------------- | -------------------------------- |
| `CLOUD_REGION`                   | AWS region or GKE location       |
| `CLUSTER_NAME`                   | `cluster`: `cluster_name` output |
| `AWS_ROLE_ARN`                   | AWS deployment role              |
| `GCP_PROJECT_ID`                 | GCP project                      |
| `GCP_WORKLOAD_IDENTITY_PROVIDER` | GCP federation provider          |
| `GCP_SERVICE_ACCOUNT`            | GCP deployment service account   |

Add `OPENAI_API_KEY` as an Actions secret. External Secrets reads database credentials using its cloud identity and creates the Kubernetes Secret consumed by the backend and migration Job.

## 4. Release the application

After tests pass, CI publishes the frontend and backend container images to **GitHub Container Registry (GHCR)**. An image is the packaged app that Kubernetes runs.

Each image is tagged with the full Git commit SHA, so a release can select an exact code version. Both images support `amd64` and `arm64`. Builds cache dependencies to speed up later builds.

1. Wait for CI and image publishing to pass for the commit.
2. Open **Actions → Deploy**. Choose the cloud and environment, enter the full image SHA, and describe the workload.
3. The AI suggests how many copies of each service to run and how much CPU and memory they need. Review the saved recommendation. If it also suggests changing cloud machine or database sizes, review and apply those changes through Terraform separately.
4. The workflow runs the database migration job, starts the backend, and then starts the frontend. It waits until Argo CD has applied the requested version and both services are healthy.
5. It checks the page and API through the public Ingress address, then reports the application URL.

For example:

```bash
gh workflow run deploy.yml --ref master \
  -f cloud=aws -f environment=staging \
  -f image_tag=FULL_40_CHARACTER_COMMIT_SHA \
  -f request='Low-traffic staging for a few reviewers'
```

Use `cloud=gcp` for GCP. See the [deployment tool guide](../tools/deploy/README.md) for workflow inputs and verification details.

## Environments and previews

- **Staging** is where you check a release before production.
- **Production** is where the stable app runs.
- **PR previews** let someone try the frontend and backend from one pull request.

Staging and production each have their own infrastructure and deployment settings. A **namespace** groups an environment's resources inside Kubernetes.

Set the repository variable `PREVIEW_CLOUD` to `aws` or `gcp` to enable previews for same-repository PRs. Each preview deploys both apps and a PostgreSQL instance into its own namespace, with a persistent volume, generated credentials and a public load balancer. Previews share the staging cluster. Each preview uses its own database server. The cluster needs a default storage provisioner: EKS requires the EBS CSI driver and a default StorageClass, which the current AWS Terraform stack does not install; GKE uses Persistent Disk.

Successful PR CI triggers deployment. Updates preserve preview data. Closing the PR removes its application and database resources. See the [deployment guide](../tools/deploy/README.md) for permissions and cleanup.

## Remove the cloud setup

Remove application Ingress resources and wait for their load balancers to disappear while the controller is running. Then destroy `applications/idea-board`, `cluster-core-services`, `cluster`, and `networking`, in that order. The [Terraform guide](terraform/README.md) covers deletion protection, snapshots, and retained resources.

[Back to the project guide](../README.md).
