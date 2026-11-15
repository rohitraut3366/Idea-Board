# Cloud infrastructure

Each deployment project has its own directory, Terraform state, and plan/apply. AWS and GCP use the same structure.

```text
infra/terraform/
├── backend.json.example            # Shared S3 bucket settings for both clouds
├── aws/
│   └── staging/
│       └── ap-southeast-2/
│           ├── networking/             # VPC, subnets, routing, NAT
│           ├── cluster/                # EKS and workers
│           ├── cluster-core-services/  # Argo CD, root Application, AWS load-balancer controller
│           └── applications/
│               └── idea-board/         # RDS and its credential secret
├── gcp/
│   └── staging/
│       └── australia-southeast1/
│           ├── networking/             # VPC, subnet, NAT, private database connectivity
│           ├── cluster/                # GKE and workers
│           ├── cluster-core-services/  # Argo CD and root Application
│           └── applications/
│               └── idea-board/         # Cloud SQL and its credential secret
└── modules/                            # Reusable Terraform code
```

The directory identifies the cloud, environment, region, and project. Production uses a matching directory under `production/`, with its own resource names and configuration.

## State follows the project path

The root Makefile runs a small Python helper that calculates state locations from repository paths. For example:

| Project        | State location within its bucket                                             |
| -------------- | ---------------------------------------------------------------------------- |
| AWS networking | `infra/terraform/aws/staging/ap-southeast-2/networking.tfstate`              |
| AWS database   | `infra/terraform/aws/staging/ap-southeast-2/applications/idea-board.tfstate` |
| GCP networking | `infra/terraform/gcp/staging/australia-southeast1/networking.tfstate`        |

All projects use one S3 bucket with a separate `.tfstate` key per project and native S3 lockfiles. Both clouds use the default workspace. Environments have separate directories.

One `infra/terraform/backend.json` declares the shared S3 bucket and its AWS region. State keys are calculated automatically. Dependent projects use that same configuration and directory convention to find sibling states. The state bucket region is independent of the deployment region.

**Moving a project directory changes its state location. Migrate the state before applying from the new path.**

## Apply order

1. `networking`
2. `cluster`
3. `cluster-core-services`
4. `applications/idea-board`
5. Release the frontend and backend through Argo CD.

Cluster reads networking outputs. Core services read cluster outputs and, on AWS, networking outputs. The application reads networking outputs; on AWS it also reads the cluster's worker security group for database access.

These dependencies use `terraform_remote_state`. Apply a prerequisite before planning its consumer.

## Prepare

1. Install Terraform 1.17.x, Make, Python 3, and your cloud CLI. Use the committed provider locks.
2. Sign in to AWS for state access. For GCP deployments, also configure GCP Application Default Credentials.
3. Create one S3 state bucket with encryption, versioning, Block Public Access, and restricted access. Keep it outside these projects so it remains available during teardown.
4. Check supported Kubernetes versions and machine types in your chosen region.

AWS needs an existing cluster administrator role. Apply core services as that role, or another identity granted Kubernetes administrator access. Helm uses `aws eks get-token`.

GCP needs a billed project with Service Usage enabled. Each project enables its required APIs. Core services require `gke-gcloud-auth-plugin` and cluster administrator permissions. Helm uses Application Default Credentials.

For `cluster-core-services`, set `GITHUB_TOKEN` with Contents read/write access to this repository. The GitHub provider publishes each cluster's generated Helm values directly to `master`.

Terraform state and saved plans can contain credentials. Restrict access to both.

## Configure the shared state bucket

Run once from the repository root:

```bash
cp infra/terraform/backend.json.example infra/terraform/backend.json
```

1. Set `bucket` to the existing S3 bucket name and `region` to that bucket's AWS region.
2. Use AWS credentials with access to the state objects and permission to read, write, and delete their `.tflock` objects. Set `AWS_PROFILE` when using a named profile.
3. Use this configuration for every cloud, environment, and deployment region.

GCP Terraform commands require both AWS credentials for state access and GCP credentials for infrastructure access. Backend credentials come from the environment or AWS profile.

The local `backend.json` and project `terraform.tfvars` files are ignored by Git.

## Configure the deployment projects

1. In each of the four project directories, copy `terraform.tfvars.example` to `terraform.tfvars`.
2. Fill in the project settings. Use one stack name, such as `idea-board-staging`, throughout these projects. Choose another name for each additional environment or region.
3. For AWS, supply the existing administrator role in `cluster`.
4. For GCP, supply the project ID and other settings. Supply the database password through `TF_VAR_database_password` in your environment or CI secret store when planning the application project.

The project command supplies the deployment region from the directory path, plus the shared bucket settings and dependency state paths.

## Plan and apply one project

Start with networking. Run all Make commands from the repository root:

```bash
make init PROJECT=aws/staging/ap-southeast-2/networking
make validate PROJECT=aws/staging/ap-southeast-2/networking
make plan PROJECT=aws/staging/ap-southeast-2/networking
```

The command prints the selected project and state location. `plan` saves `project.tfplan` inside the project directory. Review its resources and costs, then apply that saved plan:

```bash
make apply PROJECT=aws/staging/ap-southeast-2/networking
make output PROJECT=aws/staging/ap-southeast-2/networking
```

Repeat for `cluster`, `cluster-core-services`, and `applications/idea-board`, in that order. For GCP, use `PROJECT=gcp/staging/australia-southeast1/...`.

Subsequent changes need a plan/apply in the affected project. When its outputs change, plan its consumers too. Additional Terraform arguments go in `ARGS`, for example:

```bash
make output PROJECT=aws/staging/ap-southeast-2/cluster ARGS=-json
```

Use an absolute path for files passed through `ARGS`; Terraform runs inside the selected project directory. To select a different Terraform executable, set `TERRAFORM=/path/to/terraform`.

`cluster-core-services` installs Argo CD chart `10.18.0` (Argo CD `v3.6.1`) and bootstraps the `cluster-core-services` root Application. The root renders child Applications from `gitops/cluster-core-services` and installs the External Secrets umbrella chart as its first child. Set `gitops_revision` in the core-services project's variables to select a pushed branch, tag or commit; it defaults to `master`.

Set `external_secrets_values` for overrides such as service-account annotations. Terraform writes them to `charts/external-secrets/values/<cloud>/<cluster-name>/values-terraform.yaml` on `master`. Argo CD selects provider and cluster files automatically and ignores missing ones. Keep the root on `master` to receive newly generated values. The file contains non-secret configuration; database credentials stay in the secret manager. Destroying the core-services project removes its generated file from GitHub.

Terraform waits for its Helm releases. Wait for each child Application to become Synced and Healthy before using its service; see [cluster services](../../gitops/cluster-core-services/README.md#deploy). Argo CD manages the operator's installation and updates from Git.

AWS Load Balancer Controller chart `3.6.3` is installed by Terraform. Upgrade its chart and vendored IAM policy together. GKE provides its HTTP load-balancing controller through the cluster addon.

## Connect and release the application

1. Read `cluster_name` from the cluster project's outputs.
2. Read `database_host`, `database_port`, `database_name`, `database_username`, and `database_credential_secret_id` from the application project's outputs.
3. Configure the GitHub deployment Environment using the [deployment instructions](../../README.md#deploy-through-github-actions).
4. Run the Deploy workflow for the tested image commit.

The database module owns PostgreSQL and its credential secret together. AWS uses RDS-managed credentials; GCP stores the username and password in Secret Manager. The deployment tool supplies the Kubernetes database Secret. Migrations run in the backend's separate pre-start job.

For Argo CD access, select the cloud cluster context:

```bash
kubectl --context YOUR_CONTEXT --namespace argocd port-forward service/argocd-server 8080:443
```

Open `https://localhost:8080`. Retrieve the initial `admin` password:

```bash
kubectl --context YOUR_CONTEXT --namespace argocd get secret argocd-initial-admin-secret \
  -o jsonpath='{.data.password}' | base64 --decode
```

## Resource sizing

Worker size/count belong to `cluster`. Database size/storage/standby belong to `applications/idea-board`. The AI deployment plan writes a proposal for each:

```text
release-plan/terraform/
├── cluster/sizing.tfvars.json
└── applications/idea-board/sizing.tfvars.json
```

The generated `plan.md` contains Make commands for the two projects. Replace `YOUR_REGION` with your target region, review each proposal, and plan/apply independently.

AWS uses one NAT gateway. GCP uses regional Cloud NAT. Both databases have private addresses. Workers have a fixed count. On GCP, `node_count` must be a positive multiple of `node_zones`.

## Checks without cloud access

Each project and reusable module has provider-mock tests. Root tests substitute dependency outputs. From the repository root:

```bash
terraform -chdir=infra/terraform/aws/staging/ap-southeast-2/networking init -backend=false -input=false -lockfile=readonly
make validate PROJECT=aws/staging/ap-southeast-2/networking
make test PROJECT=aws/staging/ap-southeast-2/networking
python3 -m unittest discover -s tools/terraform/tests
```

CI discovers deployment projects under each cloud and validates/tests them and their reusable modules. It also checks generated staging and production sizing against the project configurations. Live cloud checks are still needed for IAM, service availability, Helm installation, networking, and public access.

## Existing deployments

The previous combined AWS stack was deployed, tested, and destroyed. The split projects and platform Helm installation have validation and mock-test coverage; live apply remains pending on both clouds.

### Move existing regional or GCS state

For a previously initialized project whose backend is changing:

1. Stop concurrent Terraform operations and back up its state with `terraform state pull` from the original initialized directory. Keep the backup private.
2. Configure the shared S3 bucket. Keep that directory's `.terraform` backend metadata so Terraform can find the original state. For a fresh checkout, initialize the previous configuration first.
3. Migrate one project at a time, in apply order. For example:

```bash
make init PROJECT=gcp/staging/australia-southeast1/networking ARGS='-migrate-state -input=true'
```

4. Confirm the state-copy prompt, check `make state PROJECT=... ARGS=list`, and review a normal plan before applying anything.
5. After every project is verified in S3, retire the original backend configuration and prevent further writes to its old states. Keep the backups protected.

AWS projects that already use the shared bucket, region, and calculated keys keep their existing state locations. Copy their bucket settings into the shared file and initialize normally.

### Split a combined state

For an existing deployment with a combined state:

1. Stop concurrent Terraform operations. From the original initialized checkout, back up its state with `terraform state pull > legacy.tfstate` in a private directory.
2. Configure the new projects with the existing resource names and settings. Initialize their backends.
3. Use `terraform state mv -state=legacy.tfstate -state-out=DESTINATION.tfstate` to move `module.network`, `module.cluster`, and `module.psql` into separate local state files. Keep their Terraform addresses unchanged. On GCP, move the existing `google_project_service.required` instances into their matching networking, cluster, or application project too.
4. Push each destination file through its project with `make state PROJECT=... ARGS='push /absolute/path/DESTINATION.tfstate'`. In dependency order, review/apply a refresh-only plan to publish outputs: `make plan PROJECT=... ARGS=-refresh-only`, then `make apply PROJECT=...`.
5. Check normal plans for unwanted replacements. Once verified, push the depleted legacy state through its original backend and retire the old root. Keep the backup protected.

For directory moves, use Terraform's backend migration workflow to move the existing state to the calculated destination before planning. Do not create a second state for the same resources.

Existing platform releases also need ownership migration. Import an existing Argo CD Helm release with `terraform import module.argocd.helm_release.this argocd/argocd` from the initialized core-services project, supplying its dependency variables. A `kubectl` installation or an Argo-managed controller needs a separate adoption procedure before Terraform can manage it.

## Teardown

Use `make destroy PROJECT=...` for one project at a time:

1. Remove application workloads and public routing. Wait for controller-managed load balancers to disappear.
2. Disable database deletion protection through a reviewed application-project apply, then destroy `applications/idea-board`.
3. Destroy `cluster-core-services` while the cluster is available.
4. Disable GCP cluster deletion protection through a reviewed apply, then destroy `cluster`.
5. Destroy `networking`.

AWS takes a final database snapshot by default. For disposable environments, review `database_skip_final_snapshot = true` before destruction. Check retained snapshots, backups, secrets, and load balancers. Keep the state bucket until all project states and required backups can be retired.
