# Kind verification

Verified on 16 November 2026 using the existing `kind-idea-board` cluster.

## App-of-apps and ingress run

The existing kind cluster had no application namespaces when this run started. Argo CD was installed, then one local root bootstrapped PostgreSQL, Traefik and the Idea Board parent. Every parent and child became Synced and Healthy. External Secrets Applications and CRDs were absent.

| Service        | Address                                  | Namespace            |
| -------------- | ---------------------------------------- | -------------------- |
| App            | http://localhost:8081                    | `idea-board`         |
| Staging        | http://idea-board-staging.localhost:8081 | `idea-board-staging` |
| Sample preview | http://idea-board-pr-123.localhost:8081  | `idea-board-pr-123`  |
| Argo CD        | https://localhost:8080                   | `argocd`             |

These addresses use local port-forwards on the machine running kind. Preview `123` is a local example. Use the [kind guide](../README.md) to start the demo or reopen the forwards.

| Check               | Result                                                                                                           |
| ------------------- | ---------------------------------------------------------------------------------------------------------------- |
| Bootstrap           | Root → PostgreSQL, ingress controller and Idea Board parent → backend/frontend                                   |
| Local secrets       | Kubernetes Secret from local values; External Secrets disabled                                                   |
| Request routing     | Page, built asset and API checks passed through Traefik                                                          |
| Environment parents | Staging and preview deployed through parents; frontend update followed backend readiness                         |
| Preview lifecycle   | Redeployment retained credentials; cleanup removed parent, children, namespace, database and role                |
| Failed rollout      | An intentionally unpublished frontend image produced ImagePullBackOff                                            |

Staging and preview `123` were deployed for the demo. Page and API checks through all three ingress hostnames passed, and test ideas remained isolated between the databases.

- Application image: `5ae00d82541190e313a06e14f39ddc94124455a8`.
- Chart revision: `d671dc6822ce187919c431eb177da2cdfd98cf32`.

### Load through ingress

A stack check and 1,000 concurrent create/list/delete cycles ran through `http://localhost:8081` with one backend replica:

| Concurrent cycles | Cycles | Requests | Seconds | Requests/sec | p95 request, ms | Failed requests |
| ----------------- | ------ | -------- | ------- | ------------ | --------------- | --------------- |
| 25                | 1,000  | 3,000    | 6.760   | 443.76       | 87.58           | 0               |

There were no failed cycles or cleanup failures. This was a short local load check with no configured latency threshold.

## Earlier scaling measurements

The earlier run used direct service Applications and a port-forward to frontend Nginx, then the backend and PostgreSQL. It also checked PostgreSQL pod replacement and backend restart persistence. These measurements predate the ingress run above. Each cycle created an idea, read the list, and deleted that idea. Test data was removed successfully.

| Backend replicas | Concurrent cycles | Cycles | Requests | Seconds | Requests/sec | p95 request, ms | Failed requests |
| ---------------- | ----------------- | ------ | -------- | ------- | ------------ | --------------- | --------------- |
| 1                | 10                | 1,000  | 3,000    | 7.627   | 393.32       | 44.43           | 0               |
| 1                | 25                | 1,000  | 3,000    | 8.155   | 367.87       | 113.61          | 0               |
| 1                | 50                | 1,000  | 3,000    | 7.478   | 401.18       | 204.25          | 0               |
| 2                | 50                | 1,000  | 3,000    | 5.226   | 574.09       | 138.66          | 0               |
| 2                | 50                | 10,000 | 30,000   | 55.282  | 542.68       | 144.14          | 0               |

All 42,000 measured requests passed, with no failed cycles or cleanup failures. No latency threshold was configured. The longer run lasted about 55 seconds; these are short local measurements, not a soak test or a production capacity guarantee.

The controlled comparison at concurrency 50 improved from 401 to 574 requests/second when the backend went from one replica to two. Repeated runs and longer observation would be needed to establish a reliable capacity limit.

The [raw results](evidence/load-results.json) contain the earlier test outputs. To repeat a run against staging, first leave `kubectl --context kind-idea-board --namespace idea-board-staging port-forward service/frontend 3002:80` running in another terminal:

```bash
IDEA_BOARD_BASE_URL=http://127.0.0.1:3002 LOAD_CYCLES=1000 LOAD_CONCURRENCY=50 \
  npm --prefix apps/frontend run test:load
```

For a new scaling comparison through ingress, use the base app URL from the kind guide or a separate frontend port-forward to staging. Set `backend.replicas` to `2` in a copy of the recorded recommendation and release it with the same staging command in the kind guide. Repeat the load command, then release the original recommendation to return to one replica.

## Earlier scaling test setup

- One ARM64 kind node, Kubernetes `v1.33.1`, Argo CD `v3.6.1`, PostgreSQL `17`.
- Docker reported 16 CPUs and 40.95 GiB available memory. The machine also ran other containers.
- Staging and preview image/chart revision: `5ae00d82541190e313a06e14f39ddc94124455a8`.
- Backend: one Uvicorn process per pod, CPU request `100m`, memory request/limit `128Mi`/`256Mi`.
- Frontend: one replica, CPU request `50m`, memory request/limit `32Mi`/`128Mi`.
- PostgreSQL: CPU request `100m`, memory request/limit `64Mi`/`256Mi`, `max_connections = 100`.

The backend's measured pool configuration permits five pooled connections plus ten overflow connections per process. Two staging replicas can therefore open up to 30 connections. The original app, preview, migrations, and administration also use connections and must be included before raising replica limits. This is configuration arithmetic, not a measured database saturation point.

## AI recommendation

The assistant generated a [recommendation](evidence/recommendation.json) for this local setup during the verification session. The deployment tool validated it, generated a release plan, and used it to deploy the persistent staging and preview services.

The integration test uses fixed recommendations so it can run independently of a model. This interactive AI session does not verify the GitHub Actions AI runner's authentication.

## Verification boundary

The app-of-apps run bootstrapped application resources into an existing kind cluster. Creating the kind cluster on a fresh machine was not exercised. The earlier scaling measurements used the setup described above.

Metrics Server was unavailable, so per-pod CPU and memory under load were not measured. Cloud networking, managed database access, cloud secret access, and public load balancers were not exercised. The independent AWS and GCP stacks have validation and provider-mock tests, with no current public application URLs.
