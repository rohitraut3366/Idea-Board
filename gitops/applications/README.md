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
    cascadeDelete: true
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
2. Declare its chart path, Helm settings and destination namespace under `applications` in each provider values file where it should run.
3. Set `enabled: true` in those entries.
4. Allow its namespace and resource types in the bootstrap AppProject.

Disabling an app removes its child Application. `cascadeDelete: true` also removes that child's installed resources. External Secrets keeps cascading deletion and automatic pruning disabled. Review its installed resources separately when retiring the operator.
