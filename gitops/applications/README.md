# GitOps Applications

One chart renders the Argo CD Applications for cluster services and application environments. Values files decide which Applications run.

```text
gitops/applications/
├── Chart.yaml
├── values.yaml                  # Shared settings; empty applications map
├── values-kind.yaml             # Full kind app declarations
├── values-aws.yaml              # Full AWS app declarations
├── values-gcp.yaml              # Full GCP app declarations
└── templates/applications.yaml  # Shared Application template
```

Each service has its own chart under `charts/`. The backend's kind override enables its PostgreSQL child chart.

## Select applications

Each provider file declares its apps, including their chart paths, namespaces and Helm settings. The default `values.yaml` contains shared settings and an empty `applications` map.

For example, the backend entry in `values-kind.yaml` includes:

```yaml
applications:
  backend:
    enabled: true
    source:
      path: charts/idea-board-backend
      helm:
        releaseName: backend
        skipTests: true
        valueFiles:
          - values-kind.yaml
```

`gitops/applications/values-kind.yaml` selects the local services. Their settings stay in each service's chart. Staging and preview parents use the same shared template with their own enabled services, namespaces, image tags and sizing.

## Bootstrap the root

The bootstrap chart in `infra/terraform/modules/argocd/bootstrap` creates the `idea-board` AppProject and root Application. The root points to this chart. The bootstrap selects `values-aws.yaml`, `values-gcp.yaml` or `values-kind.yaml` from the cloud Terraform passes in. The cloud and cluster name also reach the root, so each child Application can select its service-specific overrides.

- **kind:** install Argo CD, then apply the bootstrap chart manually. Follow the [kind guide](../README.md).
- **AWS or GCP:** apply the cloud's Terraform `cluster-core-services` project. It installs Argo CD and the same bootstrap chart. Follow the [Terraform guide](../../infra/terraform/README.md).

The cloud profiles enable External Secrets. Application releases use their environment settings and database credentials through the deployment workflow.

Wait for the root and each enabled child to become Synced and Healthy:

```bash
kubectl --context YOUR_CONTEXT --namespace argocd get applications --watch
```

## Service overrides

For local settings, a child Application selects `values-kind.yaml` from its own chart.

Each root values file lists the External Secrets child’s `helm.valueFiles` and sets `ignoreMissingValueFiles: true`. The AWS and GCP entries load these files from the service chart in order:

```text
values.yaml
values/<cloud>/values.yaml
values/<cloud>/<cluster-name>/values.yaml
values/<cloud>/<cluster-name>/values-terraform.yaml
```

Provider and cluster files are optional. Terraform publishes generated settings, such as the External Secrets service-account annotation, to `values-terraform.yaml`. The child uses `ignoreMissingValueFiles: true` and picks up a file when it appears on the watched Git branch. A pinned revision uses the files at that revision.

The paths use `{{ .Values.clusterName }}` for the cluster name passed by the bootstrap. The shared template renders the declared Helm settings.

Keep credentials in the cloud secret manager. Generated values contain configuration references.

## External Secrets identity

The cloud's `cluster-core-services` project calls its own `modules/<cloud>/external-secrets` module. That module creates the operator's identity and publishes its Helm values automatically.

- **AWS:** the cluster module registers the EKS OIDC issuer with IAM once. External Secrets gets an IRSA role for `external-secrets/external-secrets`, read access to all Secrets Manager secrets in the account, and the `eks.amazonaws.com/role-arn` service-account annotation.
- **GCP:** creates a Google service account, binds `external-secrets/external-secrets` through Workload Identity, and grants Secret Manager read access across the project. It generates the `iam.gke.io/gcp-service-account` annotation.

AWS uses the public [IAM OIDC role module](https://github.com/terraform-aws-modules/terraform-aws-iam/tree/v5.52.1/modules/iam-assumable-role-with-oidc), pinned to `5.52.1`. For an existing EKS cluster, apply the `cluster` project first to register its OIDC issuer.

The module writes `charts/external-secrets/values/<cloud>/<cluster-name>/values-terraform.yaml` on `master`, using the shared [GitHub values module](../../infra/terraform/modules/github/helm-values). The generated file contains identity references, not credentials.

```text
cluster-core-services
└── External Secrets Terraform module
    ├── Cloud identity and read permissions
    └── Generated values file → Argo CD → annotated operator service account
```

Apply the core-services project to create or update this setup. General chart overrides belong in the chart's provider or cluster values files.

## Add a service

1. Add its Helm chart under `charts/`.
2. Declare its chart path, Helm settings and destination namespace under `applications` in each provider values file where it should run.
3. Set `enabled: true` in those entries.
4. Allow its namespace and resource types in the bootstrap AppProject.

Every child Application has Argo CD’s cascading deletion finalizer. Disabling or deleting a child Application also deletes its managed resources. External Secrets keeps automatic pruning disabled during sync.
