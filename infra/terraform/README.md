# Cloud infrastructure

Terraform provisions Kubernetes, managed PostgreSQL, and the network between them on AWS or GCP. The application uses the same containers and Helm charts on either cloud.

Choose the `aws` or `gcp` directory, supply that cloud's configuration, and run Terraform there. These are separate roots because EKS and GKE have different APIs and access controls. Keeping them explicit makes the code easier to read than a single root full of provider conditions.

## Layout

```text
terraform/
├── aws/                         # AWS provider, state, inputs, and module calls
├── gcp/                         # GCP provider, state, inputs, and module calls
└── modules/
    ├── aws/
    │   ├── network/
    │   ├── cluster/
    │   └── psql/
    └── gcp/
        ├── network/
        ├── cluster/
        └── psql/
```

Each module has `main.tf`, `variables.tf`, `outputs.tf`, `versions.tf`, and its own `tests/`. Cluster IAM resources are in `iam.tf` so the cluster configuration stays readable. The parents call modules named `network`, `cluster`, and `psql` and pass their outputs directly to the next module.

| Module    | AWS                                                                                         | GCP                                                                                                 | Why it is separate                                                                                          |
| --------- | ------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------- |
| `network` | VPC, public and private subnets, internet gateway, NAT gateway, routes                      | VPC, subnet, pod and service ranges, Cloud Router/NAT, Private Service Access                       | Owns address allocation and connectivity; both other modules use it.                                        |
| `cluster` | EKS control plane, managed EC2 workers, IAM roles, administrator access, control-plane logs | Regional GKE Standard control plane, worker pool, dedicated node service account, Workload Identity | Owns Kubernetes capacity and access without managing application releases.                                  |
| `psql`    | RDS PostgreSQL 17, subnet group, security group, managed password                           | Cloud SQL PostgreSQL 17, database, user, Secret Manager credential                                  | Owns database capacity, backups, and connectivity. Application migrations remain a separate deployment Job. |

## How traffic flows

On AWS, workers run in private subnets across the selected zones. A NAT gateway in the first public subnet lets them pull public GHCR images. The RDS security group accepts port 5432 only from the EKS security group attached to managed workers. RDS has no public endpoint.

On GCP, workers use private addresses. Cloud NAT provides internet egress, and secondary subnet ranges supply pod and service addresses. Private Service Access connects the VPC to Cloud SQL, which has no public IPv4 address. Reachability is VPC-based; PostgreSQL credentials and TLS are still required. Private Service Access reserves a separate, automatically selected /16 range.

Both Kubernetes APIs are reachable over their public endpoints without a caller IP allowlist. AWS access requires IAM authentication and an EKS access entry; this code grants cluster administration to `admin_role_arn`. GCP access requires Google credentials and the appropriate IAM and Kubernetes permissions. AWS also enables the private endpoint. GKE uses a separate `/28` control-plane range. Keep every configured range clear of existing VPC, VPN, peering, and on-premises networks.

AWS subnet allocation expects a `/16` VPC: the first public subnets start at offsets 0, 1, and 2, while private subnets start at 128, 129, and 130. For `10.10.0.0/16`, the first public/private pair is `10.10.0.0/24` and `10.10.128.0/24`. Supply two or three distinct availability zones and keep their ordering stable.

## Before deploying

Use Terraform 1.17.x. Provider versions and checksums are recorded in each root's `.terraform.lock.hcl`; commit deliberate provider upgrades with those lock files.

You need your own cloud account or project, billing, credentials, quotas, and a remote state bucket. Review the expected bill before applying: the control plane, workers, database, NAT, storage, logs, and network traffic can all incur charges while the application is idle.

For AWS, supply an existing administrator IAM role in `admin_role_arn`. The identity running Terraform needs permission to provision the resources in these modules, pass the EKS roles, and create EKS access entries. Use your normal AWS profile or workload identity; do not put access keys in Terraform files.

For GCP, use Application Default Credentials or workload identity for a project with billing and the Service Usage API already enabled. The deploying identity needs permission to enable the listed APIs and manage networking, GKE, service accounts/project IAM, Cloud SQL, and secrets. Terraform enables the remaining APIs and leaves them enabled on destroy. Kubernetes administrator access follows your GCP IAM and Kubernetes permissions.

Free Plan accounts can restrict EC2 types and RDS backup retention even when a plan succeeds. Check eligible workers with `aws ec2 describe-instance-types --filters Name=free-tier-eligible,Values=true`. This account required `node_instance_type = "t3.small"` and `database_backup_retention_days = 1`; the general defaults remain `t3.medium` and seven days.

Check regional Kubernetes versions and instance availability before choosing values. GKE requires a REGULAR-channel version **1.36.4-gke.1469000 or newer** so it can create the cluster without a temporary default node pool. Its version input is a minimum: the release channel can select a newer version and upgrade it later. EKS takes the requested supported minor version. The example files deliberately leave versions unset rather than guessing regional availability.

## State

Create the state bucket separately so destroying the application stack cannot destroy its own state. Use a different state key or prefix for each environment, and give each deployed stack a distinct `name`.

For S3, enable bucket versioning, encryption, and Block Public Access. The backend example enables native S3 lock files; no DynamoDB table is needed. The Terraform identity needs access to the state object and permission to read, write, and delete its `.tflock` object.

For GCS, enable bucket versioning, uniform bucket-level access, and public access prevention. GCS state locking is built in. Restrict object access to the deployment identities and operators who need it.

Both backends encrypt data at rest. State can contain credentials, especially the GCP SQL password and Secret Manager payload. `sensitive = true` hides ordinary CLI output; it does not remove values from state. Protect state versions and saved plans as secrets. Local state, plans, `terraform.tfvars`, and `backend.hcl` are ignored by Git.

## Configure and run

From the repository root, choose one cloud:

```bash
cd infra/terraform/aws
# Or: cd infra/terraform/gcp
cp terraform.tfvars.example terraform.tfvars
cp backend.hcl.example backend.hcl
```

Edit both files before proceeding. Replace the example account/project, state bucket, administrator role ARN, zones, and Kubernetes version. Keep the stack name between 3 and 24 lowercase letters, digits, or hyphens, starting with a letter and ending with a letter or digit, so it also fits the GCP node identity.

GCP additionally requires `TF_VAR_database_password` in the process environment. Supply a generated password through your password manager or CI secret store, rather than committing it to a variable file. AWS generates and manages its database password through RDS.

```bash
terraform init -backend-config=backend.hcl
terraform validate
terraform plan -out=stack.tfplan
# Review the saved plan before applying it.
terraform apply stack.tfplan
terraform output
```

Use the same cloud credentials and backend configuration for subsequent runs. Do not point two stacks at the same state key. Stage and production can use the same code with separate names, variable files, and state locations; this code does not create those environments automatically.

Both roots expose the same output names:

| Output                                            | Use                                                                   |
| ------------------------------------------------- | --------------------------------------------------------------------- |
| `cluster_name`                                    | Select the cluster when generating kubeconfig.                        |
| `database_host`, `database_port`, `database_name` | Build the PostgreSQL connection string.                               |
| `database_username`                               | Initial database owner.                                               |
| `database_credential_secret_id`                   | Retrieve the password from AWS Secrets Manager or GCP Secret Manager. |

## Connect the application

After applying, generate kubeconfig with `aws eks update-kubeconfig` or `gcloud container clusters get-credentials`, supplying the cluster name and region. Check the selected context before deploying anything.

The existing backend chart expects a Kubernetes Secret containing `IDEA_BOARD_DATABASE_URL`. Retrieve the credentials using the secret reference, URL-encode them, and construct a `postgresql+psycopg://` URL with the database outputs and `sslmode=require`. Deliver that Secret through your deployment process. Terraform does not read back the password or write Kubernetes Secrets. For certificate identity verification, configure the cloud CA and the driver's verification settings before production use.

The initial database owner is a bootstrap identity. Create a narrower application user for production and keep its permissions and rotation separate from database administration. When credentials rotate, update the Kubernetes Secret and restart the workloads that read it through environment variables. RDS-managed owner credentials rotate independently of this code.

Deploy the existing backend and frontend charts through Argo CD. The backend migration Job runs before the backend starts. After cluster creation, follow the [separate ingress setup](../ingress/README.md). AWS has a post-cluster Terraform root for controller IAM/Pod Identity and an Argo controller Application; GCP enables its built-in HTTP load-balancing controller in the cluster module. Ingress resources then let controllers own public load balancers and pod registration. Argo CD installation, DNS, certificates, and application releases remain separate deployment steps. The current kind configuration remains local to kind.

## Capacity and availability

The defaults start with two workers and a small, single-zone database. They are a starting size, not a production sizing recommendation.

| Setting               | AWS                        | GCP                                            |
| --------------------- | -------------------------- | ---------------------------------------------- |
| Total workers         | `node_count`               | `node_count`, evenly split across `node_zones` |
| Worker size           | `node_instance_type`       | `node_machine_type`                            |
| Database size         | `database_instance_class`  | `database_tier`                                |
| Initial database disk | `database_storage_gb`      | `database_storage_gb`                          |
| Database standby      | `database_multi_az = true` | `database_regional = true`                     |

Workers have a fixed count; this code does not install a cluster autoscaler. On GCP, the total must be a positive multiple of the number of worker zones. GKE repairs and upgrades workers automatically. EKS node upgrades follow Terraform changes. EKS worker groups use unique name prefixes and are created before their predecessors are deleted, so a replacement can become ready while an old group is draining or being removed.

AWS uses **one NAT gateway** to keep the initial setup smaller. Its zone is an egress failure point, and traffic from the other zones can incur cross-zone charges. A production availability design should use NAT per zone. GCP Cloud NAT is regional. RDS uses the configured disk size; Cloud SQL can grow its disk automatically and does not shrink it afterward. RDS keeps seven days of automated backups by default; Cloud SQL retains seven automated backups and enables point-in-time recovery.

For a capacity test, increase workers and the database size in the environment's variables, review/apply the plan, then run application load from a separate load generator. Measure error rate, request latency, pod CPU/memory, database connections/CPU, and resource saturation. Restore the intended size afterward. The Terraform tests below verify sizing configuration; they do **not** measure application scale or cloud performance.

## Checks without cloud accounts

CI runs formatting, schema validation, and native Terraform tests. Every test file declares a mock provider, so tests do not authenticate to AWS/GCP or create resources. Tests live with each module; root tests also exercise the combined module graph and shared outputs.

From `infra/terraform`, check formatting:

```bash
terraform fmt -check -recursive
```

Then validate and test one root:

```bash
terraform -chdir=aws init -backend=false -input=false -lockfile=readonly
terraform -chdir=aws validate
terraform -chdir=aws test
```

Use `gcp` for the other cloud. `-backend=false` leaves remote state untouched; mocked tests use their own test state. To check an individual module using the same provider lock as its root:

```bash
cp aws/.terraform.lock.hcl modules/aws/network/.terraform.lock.hcl
terraform -chdir=modules/aws/network init -backend=false -input=false -lockfile=readonly
terraform -chdir=modules/aws/network validate
terraform -chdir=modules/aws/network test
```

Repeat for `cluster` and `psql`, or for GCP. CI also validates and mock-plans the separate AWS controller setup. Tests cover private networking, public API reachability, the AWS administrator role, database protection and credentials, worker placement/count, and larger database configurations.

Mocked tests cannot establish cloud permissions, quotas, regional version support, API acceptance, or actual connectivity. A live check should include plan/apply, application deployment, migrations, database requests from the backend, a second plan for drift, and teardown in a disposable environment.

## Live verification

The AWS stack was deployed in Sydney (`ap-southeast-2`) with two `t3.small` workers and private RDS PostgreSQL. Both frontend and backend Argo CD Applications reached Synced and Healthy. Health checks, migrations, idea create/read/delete, frontend assets and API proxying, pagination, input validation, and duplicate prevention passed. A second Terraform plan reported no changes.

A small concurrency check completed 50 create/read/delete cycles: 150 requests at concurrency 10, with zero errors in 12.89 seconds. The p95 time for a complete three-request cycle was 2.741 seconds. Requests used a temporary Kubernetes port-forward; this checks concurrent application behavior, but does not establish production capacity or public ingress performance. The capacity test described above remains pending.

Terraform then destroyed all 31 stack resources. A follow-up cleanup confirmed no retained database backups, database or disk snapshots, worker disks, project logs, or secrets. The separate state bucket and all 37 saved object versions/delete markers were also deleted. Recreate the state bucket before deploying again. GCP verification is limited to schema validation and mocked tests; live plan/apply, application checks, and teardown are still pending.

## Teardown

Deletion protection is enabled by default. To intentionally remove a stack, first set `deletion_protection = false`, review/apply that change, and then review a destroy plan. AWS protects RDS; GCP protects both GKE and Cloud SQL.

RDS takes a final snapshot named `<name>-final` by default. For a disposable verification run, set `deletion_protection = false` and `database_skip_final_snapshot = true` before applying; that run will not retain a final snapshot. If that snapshot already exists from an earlier teardown, rename or remove it before destroying another database with the same stack name. Retained snapshots, backups, secret recovery periods, and the separately managed state bucket may continue to incur charges. Destroying this stack does not disable GCP project APIs or delete the state bucket.
