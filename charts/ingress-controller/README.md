# Local ingress controller

This umbrella chart installs Traefik for kind. The `idea-board` Argo CD root manages it through the `ingress-controller` Application.

`values.yaml` configures the `traefik` IngressClass and HTTP NodePort `30080`. The controller reads standard Kubernetes Ingress resources. Add local overrides here; upstream dependency versions are pinned in `Chart.yaml` and `Chart.lock`.

```bash
helm repo add traefik https://traefik.github.io/charts
helm dependency build charts/ingress-controller
```

See the [kind guide](../../gitops/README.md) for bootstrap, port mapping and application URLs.
