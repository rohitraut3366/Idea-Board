# Cluster services

Terraform installs Argo CD and creates a root Application named `cluster-core-services`. The root reads this directory and creates a child Application for each service. Argo CD installs and updates those services.

```text
cluster-core-services
└── external-secrets
    └── External Secrets Operator
```

Both AWS and GCP use this setup. The first child installs our External Secrets umbrella chart in the `external-secrets` namespace. It wraps upstream chart `2.15.0` with our defaults and overrides.

## Files

```text
infra/terraform/modules/argocd/
├── main.tf                      # Argo CD installation and root bootstrap
└── bootstrap/
    └── templates/
        ├── project.yaml         # Allowed repositories, namespaces and resource types
        └── root.yaml            # Root Application

gitops/cluster-core-services/
├── Chart.yaml                   # Renders the child Applications
├── values.yaml                  # Applications, Git revision, cloud and cluster
└── templates/
    └── applications.yaml        # Creates a child Application for each values entry

charts/external-secrets/
├── Chart.yaml                   # Pinned upstream dependency
├── Chart.lock                   # Locked dependency resolution
├── values.yaml                  # Operator defaults
└── values/
    └── <cloud>/<cluster-name>/
        └── values-terraform.yaml # Published by Terraform on apply
```

## Deploy

1. Apply `networking` and `cluster` using the [Terraform instructions](../../infra/terraform/README.md).
2. Set `GITHUB_TOKEN` with repository Contents read/write permission. Terraform uses it to publish generated values to `master`.
3. Plan and apply the cloud's `cluster-core-services` project. The root watches `master`; set `gitops_revision` in that project's `terraform.tfvars` to select another pushed branch, tag or commit.
4. Select the cloud cluster context and wait for the root to sync, then for the service to become ready:

```bash
kubectl --context YOUR_CONTEXT --namespace argocd wait application/cluster-core-services \
  --for=jsonpath='{.status.sync.status}'=Synced --timeout=10m
kubectl --context YOUR_CONTEXT --namespace argocd wait application/external-secrets \
  --for=jsonpath='{.status.sync.status}'=Synced --timeout=10m
kubectl --context YOUR_CONTEXT --namespace argocd wait application/external-secrets \
  --for=jsonpath='{.status.health.status}'=Healthy --timeout=10m
kubectl --context YOUR_CONTEXT --namespace argocd get applications
```

Terraform waits for the Argo CD Helm installation and root bootstrap. The commands above wait directly for External Secrets Operator. Wait for each child Application to be Synced and Healthy as you add services.

## Update a service

Edit the umbrella chart's `values.yaml` or dependency version, then merge the change into the watched Git branch. Argo CD applies it automatically.

To add a service, give it its own umbrella chart directory under `charts/`, add an entry under `applications` in this directory's `values.yaml`, and allow its namespace and resource types in the bootstrap project.

For environment-specific overrides, set `external_secrets_values` in the cloud's `cluster-core-services/terraform.tfvars`. For example, to attach an existing IRSA role on EKS:

```hcl
external_secrets_values = {
  serviceAccount = {
    annotations = {
      "eks.amazonaws.com/role-arn" = "arn:aws:iam::ACCOUNT_ID:role/external-secrets"
    }
  }
}
```

Apply the core-services project to publish these settings in `charts/external-secrets/values/<cloud>/<cluster-name>/values-terraform.yaml` on `master`. The shared [GitHub values module](../../infra/terraform/modules/github/helm-values) manages the file. The IAM role needs secret-read permissions and an OIDC trust policy for `system:serviceaccount:external-secrets:external-secrets`.

The root passes the cloud and cluster name to every child. Each child loads its chart defaults, optional provider and cluster settings, and the generated file in that order. `ignoreMissingValueFiles: true` lets the service start before optional files exist. When a file is committed, Argo CD picks it up through the watched Git branch. A pinned commit keeps the files from that commit.

Automatic sync repairs drift. Removing a file does not automatically delete a cluster service. The Applications have no cascading deletion finalizer, so deleting an Application also leaves its installed resources in place. Review and remove those resources explicitly when retiring a service.

## Database credentials

This bootstrap installs the operator. AWS IAM access, the `SecretStore` connection and Idea Board's `ExternalSecret` are still needed to pull database credentials from AWS Secrets Manager. Those application resources belong with Idea Board's deployment configuration.

## Check on kind

With Argo CD running in the existing `kind-idea-board` cluster, use a pushed revision containing these files:

```bash
python3 gitops/tests/check_core_services.py --context kind-idea-board --revision YOUR_GIT_REVISION
```

This installs the root bootstrap, waits for the root and operator to become Synced and Healthy, and checks that the External Secrets CRDs are established. CI runs this check before the application release checks.
