# External Secrets Operator

This umbrella chart pins the upstream operator in `Chart.yaml`. Our defaults live in `values.yaml`, under `external-secrets:`. Use that key for upstream settings such as service-account annotations, resources and replica counts.

```bash
helm repo add external-secrets https://charts.external-secrets.io
helm dependency build charts/external-secrets
helm lint charts/external-secrets --strict
helm template external-secrets charts/external-secrets --namespace external-secrets
python3 -m unittest discover -s charts/external-secrets/tests
```

After changing the dependency version, run `helm dependency update charts/external-secrets --skip-refresh` and commit `Chart.yaml` with `Chart.lock`.

The [cluster services root Application](../../gitops/cluster-core-services/README.md) deploys this chart and passes environment overrides from the core-services Terraform project.
