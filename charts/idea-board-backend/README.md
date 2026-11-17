# Backend Helm chart

Deploys the FastAPI backend and a ClusterIP Service on port `8000`. A separate Job runs `alembic upgrade head` before the backend deployment. A failed migration blocks the deployment. Failed Jobs remain for inspection until the next attempt; successful Jobs are removed.

By default, the chart uses an existing PostgreSQL database and a Kubernetes Secret containing `DATABASE_URL`. Use a `postgresql+psycopg://` URL. Both the backend and migration Job read that key as an environment variable.

## Install

```bash
helm dependency build charts/idea-board-backend
helm upgrade --install backend charts/idea-board-backend \
  --namespace idea-board \
  --set databaseSecretName=idea-board-database \
  --set image.repository=ghcr.io/rohitraut3366/idea-board-backend \
  --set image.tag=YOUR_COMMIT \
  --wait --timeout 5m
```

## Cloud database credentials

The application’s Terraform project publishes this file through the GitHub provider:

```text
charts/idea-board-backend/values/<cloud>/<cluster-name>/values-terraform.yaml
```

It supplies the `externalSecret` subchart values: the Kubernetes Secret name, cloud provider and `dataFrom` secret references. Terraform builds the complete connection URL and stores it under `DATABASE_URL` in the cloud secret manager. External Secrets uses the operator’s IRSA role on AWS or Workload Identity on GCP and `dataFrom.extract` to copy the secret’s JSON fields into Kubernetes.

```text
Terraform → generated values → Argo CD → SecretStore → ExternalSecret
                                                            ↓
                                                  Kubernetes database Secret
                                                            ↓
                                                   migration Job → backend
```

The SecretStore uses wave -3, the ExternalSecret uses wave -2, and the migration Job uses a Sync hook at wave -1. The generated Secret contains `DATABASE_URL`. Terraform encodes the credentials and enables TLS in the URL. The connection URL stays in Terraform state, the cloud secret manager and Kubernetes; GitHub stores only the secret reference.

After changing the connection URL in Terraform, apply the application project and restart backend pods once External Secrets refreshes the Kubernetes Secret.

The reusable [external-secret-config chart](../external-secret-config/README.md) renders these resources. It is disabled by default; Terraform enables it for cloud deployments. The operator itself remains a cluster core service.

## Local PostgreSQL

The chart includes an optional PostgreSQL child chart in `charts/postgres`. It is disabled by default. The local `values-kind.yaml` enables it:

```yaml
postgres:
  enabled: true
  fullnameOverride: postgres
  password: idea_board_local
```

The child chart creates PostgreSQL and its persistent volume. The backend chart creates the database connection Secret. Argo CD deploys them in this order:

```text
PostgreSQL and database Secret → migration Job → backend
          wave -2                  wave -1        wave 0
```

The local migration Job uses a `Sync` hook so PostgreSQL can start first. With a pre-existing Kubernetes database Secret, migrations use the `PreSync` hook for Argo CD and pre-install/pre-upgrade hooks for Helm. When External Secrets creates the Secret, migrations use the Sync hook after the secret resources. A failed migration blocks backend deployment in Argo CD.

Use the [kind guide](../../gitops/README.md) to deploy the local profile. Local data survives pod replacement; the volume is retained when the PostgreSQL resources are pruned or the Helm release is removed. Deleting the namespace or cluster removes the data.

The chart defaults select a published GHCR image. Override `image.tag` to select another release.

The Service name matches the Helm release name: `backend` in this example. The frontend chart defaults to connecting to `backend:8000` in the same namespace. The charts are separate releases and can be upgraded independently.

## Configuration

| Value                    | Default                                    | Purpose                                                   |
| ------------------------ | ------------------------------------------ | --------------------------------------------------------- |
| `databaseSecretName`     | Required for an existing Secret            | Existing Secret with `DATABASE_URL`; cloud deployments use `externalSecret.secretName` |
| `image.repository`       | `ghcr.io/rohitraut3366/idea-board-backend` | Container repository                                      |
| `image.tag`              | Published commit tag                       | Image tag; use a commit tag for published images          |
| `image.pullPolicy`       | `IfNotPresent`                             | Image pull policy                                         |
| `replicas`               | `1`                                        | Backend replicas                                          |
| `externalSecret.enabled` | `false`                                    | Create the cloud database Secret through External Secrets |
| `postgres.existingSecret` | Empty | Existing Secret containing `POSTGRES_PASSWORD` for bundled PostgreSQL |
| `postgres.enabled`       | `false`                                    | Deploy the local PostgreSQL child chart                   |
| `resources`              | See `values.yaml`                          | Backend and migration Job resource requests and limits    |

Readiness uses `/health`; startup and liveness use TCP probes. A database outage removes traffic without repeatedly restarting healthy API processes. Pods run as non-root, disable privilege escalation, and do not mount service-account tokens.

With an external database, the database and Secret must exist before the migration hook runs. Helm rollback restores application manifests, not database migrations; migrations must remain compatible with the previous application version.

For local staging and PR previews, the deployment tool selects `values-postgres.yaml`. Each namespace gets its own PostgreSQL Deployment and volume. The tool creates a stable Kubernetes Secret with `DATABASE_URL` for the backend and `POSTGRES_PASSWORD` for PostgreSQL. `postgres.existingSecret` selects this Secret, so credentials are referenced rather than stored in Argo CD Application values.

## Ingress health configuration

The frontend chart's Ingress routes `/api` directly to this backend Service. AWS values set the Service's `alb.ingress.kubernetes.io/healthcheck-path` to `/health`. GCP values annotate the Service for a network endpoint group and its BackendConfig; `gcpBackendConfig: true` creates that health configuration with path `/health` on pod port 8000. The backend chart does not create another Ingress or a public Service. See the [ingress guide](../../infra/ingress/README.md) for setup and ownership.
