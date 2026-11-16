# External Secret configuration

Creates a SecretStore and ExternalSecret for an application. The External Secrets Operator must already be installed in the cluster.

The backend includes this chart as the `externalSecret` dependency. Terraform supplies its cloud settings:

```yaml
externalSecret:
  enabled: true
  fullnameOverride: backend-database
  secretName: idea-board-database
  provider:
    aws:
      service: SecretsManager
      region: ap-southeast-2
  dataFrom:
    - extract:
        key: <cloud-secret-reference>
```

GCP uses `provider.gcpsm.projectID` instead of `provider.aws`. The operator uses its own cloud identity to read the secret's JSON fields and copy them into the Kubernetes Secret named by `secretName`.

`fullnameOverride` names the SecretStore and ExternalSecret. Without an override, they use `<release>-secrets`. The SecretStore runs in Argo CD wave -3 and the ExternalSecret in wave -2, before the backend migration at wave -1.

To reuse this chart, add a `file://../external-secret-config` dependency to another application chart and supply its provider, target Secret name and `dataFrom` list.
