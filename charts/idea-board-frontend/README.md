# Frontend Helm chart

Deploys the React web app served by Nginx and a ClusterIP Service on port `80`. Nginx forwards `/api` to the configured backend Service. This chart is independent of the backend chart and does not run migrations.

## Install

Deploy the backend first, then install the frontend:

```bash
helm upgrade --install frontend charts/idea-board-frontend \
  --namespace idea-board \
  --set image.repository=ghcr.io/rohitraut3366/idea-board-frontend \
  --set image.tag=YOUR_COMMIT \
  --set backendUpstream=backend:8000 \
  --wait --timeout 5m
```

For local kind, use `--kube-context kind-idea-board` and `-f gitops/kind/frontend-values.yaml` instead of the image overrides. Those values point to the published GHCR commit tag.

The Service name matches the release name: `frontend` in this example. For local access:

```bash
kubectl --context kind-idea-board --namespace idea-board port-forward service/frontend 3001:80
```

Open `http://localhost:3001`. Port `3001` leaves Compose's default port `3000` available.

## Configuration

| Value | Default | Purpose |
| --- | --- | --- |
| `image.repository` | `idea-board-frontend` | Container repository |
| `image.tag` | `local` | Image tag; use a commit tag for published images |
| `image.pullPolicy` | `IfNotPresent` | Image pull policy |
| `backendUpstream` | `backend:8000` | Backend Service address and port |
| `replicas` | `1` | Frontend replicas |
| `resources` | See `values.yaml` | Container resource requests and limits |

If the backend release has a different name or namespace, set `backendUpstream` to its Service address, for example `api.idea-board.svc.cluster.local:8000`.

The container reads the upstream address at startup. Probes use `/`; the app runs as non-root, disables privilege escalation, and does not mount service-account tokens. Public routing and TLS are configured separately.

## Checks

```bash
helm lint charts/idea-board-frontend --strict
helm test frontend --namespace idea-board --logs --timeout 2m
```

The smoke test checks the frontend page and reads ideas through the API proxy. GitHub Actions installs and upgrades this chart alongside the backend chart and runs both charts' smoke tests.
