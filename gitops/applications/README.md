# GitOps Applications

One chart renders the Argo CD Applications for cluster services and application environments. Values files decide which Applications run.

```text
gitops/applications/
├── Chart.yaml
├── values.yaml                  # Application definitions; disabled by default
├── values-kind.yaml             # Enables ingress, backend and frontend
├── values-aws.yaml              # Enables External Secrets on AWS
├── values-gcp.yaml              # Enables External Secrets on GCP
└── templates/applications.yaml  # Shared Application template
```

Each service has its own chart under `charts/`. The backend's kind override enables its PostgreSQL child chart.

## Select applications

Set `enabled` in the matching values file:

```yaml
applications:
  external-secrets:
    enabled: false
  ingress-controller:
    enabled: true
  backend:
    enabled: true
  frontend:
    enabled: true
```

`gitops/applications/values-kind.yaml` selects the local services. Their settings stay in each service's chart. Staging and preview parents use the same shared template with their own enabled services, namespaces, image tags and sizing.

## Bootstrap the root

The bootstrap chart in `infra/terraform/modules/argocd/bootstrap` creates the `idea-board` AppProject and root Application. The root points to this chart and selects `values-<cloud>.yaml`.

- **kind:** install Argo CD, then apply the bootstrap chart manually. Follow the [kind guide](../README.md).
- **AWS or GCP:** apply the cloud's Terraform `cluster-core-services` project. It installs Argo CD and the same bootstrap chart. Follow the [Terraform guide](../../infra/terraform/README.md).

The cloud profiles enable External Secrets. Application releases use their environment settings and database credentials through the deployment workflow.

Wait for the root and each enabled child to become Synced and Healthy:

```bash
kubectl --context YOUR_CONTEXT --namespace argocd get applications --watch
```

## Service overrides

For local settings, a child Application selects `values-kind.yaml` from its own chart.

Services with `clusterValues: true`, including External Secrets, load these files from their chart in order:

```text
values.yaml
values/<cloud>/values.yaml
values/<cloud>/<cluster-name>/values.yaml
values/<cloud>/<cluster-name>/values-terraform.yaml
```

Provider and cluster files are optional. Terraform publishes generated settings, such as the External Secrets service-account annotation, to `values-terraform.yaml`. The child uses `ignoreMissingValueFiles: true` and picks up a file when it appears on the watched Git branch. A pinned revision uses the files at that revision.

Keep credentials in the cloud secret manager. Generated values contain configuration references.

## Add a service

1. Add its Helm chart under `charts/`.
2. Add its `source.path`, Helm settings and destination namespace under `applications` in this chart's `values.yaml`.
3. Enable it in the appropriate profile.
4. Allow its namespace and resource types in the bootstrap AppProject.

Disabling an app removes its child Application. `cascadeDelete: true` also removes that child's installed resources. External Secrets keeps cascading deletion and automatic pruning disabled. Review its installed resources separately when retiring the operator.
