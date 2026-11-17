# External Secrets Operator

This umbrella chart pins the upstream operator in `Chart.yaml`. Our defaults live in `values.yaml`, under `external-secrets:`. Use that key for upstream settings such as service-account annotations, resources and replica counts.

```bash
helm repo add external-secrets https://charts.external-secrets.io
helm dependency build charts/external-secrets
helm template external-secrets charts/external-secrets --namespace external-secrets
```

After changing the dependency version, run `helm dependency update charts/external-secrets --skip-refresh` and commit `Chart.yaml` with `Chart.lock`.

The [shared root Application](../../gitops/applications/README.md) selects values in this order, with later files overriding earlier ones:

```text
values.yaml
values/<cloud>/values.yaml
values/<cloud>/<cluster-name>/values.yaml
values/<cloud>/<cluster-name>/values-terraform.yaml
```

Missing files are ignored. Terraform publishes `values-terraform.yaml` directly to `master` when the core-services project is applied. It contains settings such as IAM role annotations. Keep credentials in the secret manager.

For automatic updates, the root and child Applications track `master`. A pinned commit uses only the values files present in that commit.
