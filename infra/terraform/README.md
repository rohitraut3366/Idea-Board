# Cloud infrastructure

Terraform defines the cloud resources. Terragrunt declares the settings and dependencies for each project. Every project has its own state and can be planned or applied separately.

```text
infra/terraform/
├── state.hcl                         # One S3 state bucket for AWS and GCP
├── root.hcl                          # Shared state and input rules
├── aws/staging/
│   ├── environment.hcl               # Stack name
│   └── ap-southeast-2/
│       ├── region.hcl                # Region and availability zones
│       ├── networking/               # VPC, subnets, routing, NAT
│       ├── cluster/                  # EKS and workers
│       ├── cluster-core-services/    # Argo CD, shared services, AWS controller
│       └── applications/idea-board/  # RDS and credential secret
├── gcp/staging/
│   ├── environment.hcl               # Stack name and GCP project selection
│   └── australia-southeast1/
│       ├── region.hcl                # Region and worker zones
│       ├── networking/               # VPC, subnet, NAT, private SQL connectivity
│       ├── cluster/                  # GKE and workers
│       ├── cluster-core-services/    # Argo CD and shared services
│       └── applications/idea-board/  # Cloud SQL and credential secret
└── modules/                          # Reusable Terraform modules
```

Each project contains its Terraform files and a `terragrunt.hcl`. The directory selects the cloud, environment, region, and project.

## Configuration

| File                                  | Settings                                                            |
| ------------------------------------- | ------------------------------------------------------------------- |
| `state.hcl`                           | Shared S3 bucket and its AWS region                                 |
| `<cloud>/staging/environment.hcl`     | Stack name; GCP project comes from `GOOGLE_CLOUD_PROJECT` or gcloud |
| `<cloud>/staging/<region>/region.hcl` | Deployment region and zones                                         |
| Each project's `terragrunt.hcl`       | Project settings and dependencies                                   |
| `root.hcl`                            | Common inputs and state-key calculation                             |

AWS staging uses Kubernetes 1.35 and two `c7i-flex.large` workers. Automated RDS backups default to disabled (`database_backup_retention_days = 0`). A positive retention value enables them. Final snapshots and deletion protection have their own settings.

GCP staging uses the declared REGULAR-channel minimum version and two `e2-standard-2` workers. Both PostgreSQL modules generate a 32-character password and store the complete connection URL under `DATABASE_URL` in AWS Secrets Manager or Google Secret Manager. Passwords and connection URLs remain in Terraform state across applies.

Change the declarations in Git when settings need to change. A production deployment needs its own environment directory, stack name, and reviewed capacity and protection settings.

## Prerequisites

1. Install Terraform 1.17.x, Terragrunt 1.2.2 (pinned in `.terragrunt-version`), kubectl, GitHub CLI, and your cloud CLI.
2. Sign in to AWS and select your profile. Both clouds need AWS access for the shared S3 state bucket.
3. Check `state.hcl` selects your existing state bucket. Protect the bucket with encryption, versioning, Block Public Access, and restricted access to state and `.tflock` objects.
4. Sign in to GitHub CLI and export `GITHUB_TOKEN="$(gh auth token)"`. The token needs repository Contents read/write access to publish cluster values to `master`.
5. For GCP, configure Application Default Credentials and select a billed project in gcloud, or set `GOOGLE_CLOUD_PROJECT`. Install `gke-gcloud-auth-plugin` for core services.

AWS cluster administration defaults to the IAM role or user behind the current login. An assumed-role session is resolved to its source IAM role. To grant another principal access, declare `admin_role_arn` in the cluster's Terragrunt `inputs`.

The identity applying core services needs Kubernetes administrator access. AWS permissions must also cover the resources in these projects. Regional capacity, account-plan restrictions, and cloud quotas still apply.

## Apply the stack

For AWS, from the repository root:

```bash
export AWS_PROFILE=idea-board
cd infra/terraform/aws/staging/ap-southeast-2
terragrunt run --all apply
```

For GCP, use `infra/terraform/gcp/staging/australia-southeast1` instead.

Terragrunt initializes the projects and applies them in this order:

```text
networking → cluster → cluster-core-services → applications/idea-board
```

Terraform reads dependency outputs from each project's state. Terragrunt's declared dependencies ensure those states exist before planning and applying their consumers. A failed project stops its dependents.

On a fresh stack, a complete plan cannot read outputs that have not been created yet. Use the ordered apply above, or review and apply one project at a time. For an existing stack:

```bash
terragrunt run --all plan
```

To work on one project, enter its directory:

```bash
cd networking
terragrunt run -- plan -out=project.tfplan
terragrunt run -- apply project.tfplan
terragrunt run -- output
```

Review the resources Terraform will create, change, or delete. The saved plan contains the selected inputs; regenerate it after changing a declaration. State and saved plans can contain credentials, so restrict access to both.

## State locations

Both clouds use the bucket and AWS region in `state.hcl`. State keys follow the repository path:

```text
infra/terraform/aws/staging/ap-southeast-2/networking.tfstate
infra/terraform/aws/staging/ap-southeast-2/cluster.tfstate
infra/terraform/gcp/staging/australia-southeast1/applications/idea-board.tfstate
```

These keys match the previous Make-based project commands. Moving a project directory changes its state key and requires a state migration first. Use the default Terraform workspace; separate environments have separate directories.

Terragrunt uses the existing bucket without changing its settings. The bucket's AWS region can differ from the deployment region. Keep it outside the application projects so teardown leaves the state available.

## Existing checkouts

1. Finish any running Terraform operation before switching to these declarations.
2. Check `state.hcl` matches the bucket and region previously recorded in `backend.json`. Terragrunt now reads `state.hcl`.
3. Move any intentional custom settings into the matching `terragrunt.hcl` inputs. Old local `tfvars` files are excluded from Terragrunt's working copy.
4. Run Terragrunt from the project or region directory. It initializes a cached working copy against the same state keys.
5. Review a normal plan before applying. AWS worker declarations now select `c7i-flex.large`; changing an existing node group's instance type can replace it. The automatic admin principal follows the selected AWS login.

If existing state is in another bucket or GCS, migrate it to the declared S3 bucket and key using the original initialized Terraform directory before switching to Terragrunt. Back up state privately and keep a single active state for each resource.

## Cluster services

The core-services project installs Argo CD and the root `idea-board` Application. Argo CD reads the shared `gitops/applications` chart with the cloud's values file. The root creates External Secrets, backend and frontend Applications. The application project publishes database references for the backend chart. External Secrets creates the Kubernetes Secret, and application releases update child configuration through this root.

AWS core services also install AWS Load Balancer Controller with its IAM permissions. GKE's HTTP load-balancing controller is enabled by the cluster project. See [public routing](../ingress/README.md).

The core-services External Secrets module creates the operator's IRSA role on AWS or Workload Identity on GCP, grants secret-read access, and publishes its service-account annotation to `charts/external-secrets/values/<cloud>/<cluster-name>/values-terraform.yaml` on `master`. Child Applications load chart defaults, provider settings, cluster settings, then generated settings. Missing files are ignored.

The root tracks `master` by default. A pinned revision uses the values present at that revision. Wait for each child Application to become Synced and Healthy; see [GitOps Applications](../../gitops/applications/README.md#bootstrap-the-root).

The `applications/idea-board` project publishes `charts/idea-board-backend/values/<cloud>/<cluster-name>/values-terraform.yaml`. It contains the Kubernetes Secret name, cloud provider and cloud secret reference. The backend child loads this file from `master`. Its `externalSecret` dependency on `charts/external-secret-config` creates a SecretStore and ExternalSecret; the operator uses its existing cloud identity to copy `DATABASE_URL` from the cloud secret into Kubernetes.

## Release the application

1. Read `cluster_name` from the cluster project's outputs.
2. Apply `applications/idea-board` to create PostgreSQL and publish the backend values file.
3. Configure the GitHub deployment Environment using the [deployment guide](../../README.md#3-configure-github-actions).
4. Run the Deploy workflow for a tested image commit. Argo CD deploys the backend and frontend, including the separate backend migration Job.

External Secrets refreshes cloud database credentials into Kubernetes. Backend processes read their Secret when they start; restart backend pods after rotating a database password.

## AI sizing proposals

The AI deployment tool writes separate proposals for the cluster and database projects. Its plan contains Terragrunt commands using those files as explicit overrides:

```text
release-plan/terraform/
├── cluster/sizing.tfvars.json
└── applications/idea-board/sizing.tfvars.json
```

Review each proposal against the committed declarations. Apply infrastructure separately from the application release. GCP worker count must be a positive multiple of the number of worker zones. Database storage cannot be reduced in place.

## Checks without cloud accounts

From the repository root:

```bash
terragrunt hcl fmt --check --working-dir infra/terraform
python3 -m unittest discover -s infra/terraform/tests
terraform -chdir=infra/terraform/aws/staging/ap-southeast-2/cluster init -backend=false -input=false -lockfile=readonly
terraform -chdir=infra/terraform/aws/staging/ap-southeast-2/cluster validate
terraform -chdir=infra/terraform/aws/staging/ap-southeast-2/cluster test
```

Terragrunt tests render the declarations without reading cloud state. Terraform provider mocks check resource configuration, automatic IAM role selection, and generated sizing. CI repeats these checks for both clouds. Live Terragrunt apply remains to be verified; cloud permissions, quotas, and public access need checks in the target account.

## Teardown

Remove application Ingress resources and let their controllers remove the load balancers first. Review database deletion protection, final snapshots, and GCP cluster deletion protection in the declarations. Apply any intended protection changes, then run from the region directory:

```bash
terragrunt run --all destroy
```

Terragrunt reverses the dependency order so core services are removed while the cluster is still available. Destroying core services also removes its generated values file from GitHub. AWS takes a final database snapshot unless `database_skip_final_snapshot = true`. Check retained snapshots, backups, secrets, and load balancers. Keep the state bucket until the project states and required backups can be retired.
