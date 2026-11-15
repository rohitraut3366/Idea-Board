# Kind verification

Verified on 16 November 2026 using the existing `kind-idea-board` cluster.

## Running demo

| Service        | Address                | Namespace            |
| -------------- | ---------------------- | -------------------- |
| App            | http://localhost:3001  | `idea-board`         |
| Staging        | http://localhost:3002  | `idea-board-staging` |
| Sample preview | http://localhost:3003  | `idea-board-pr-123`  |
| Argo CD        | https://localhost:8080 | `argocd`             |

These addresses work on the machine running the port-forwards. Preview `123` is a local example. Staging and the preview have separate databases and logins on the same PostgreSQL server; an API check confirmed they cannot see each other's ideas.

Use the [kind guide](../README.md) to start the demo or reopen its port-forwards.

## What ran

| Check                     | Result                                                                                                                                               |
| ------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------- |
| Shared services           | Root Application and External Secrets Operator Synced and Healthy; CRDs established                                                                  |
| App, staging, and preview | Page, built assets, and API checks passed on all three local addresses                                                                               |
| Persistence               | A saved staging idea survived PostgreSQL pod replacement and backend restarts using the same 1 GiB PVC                                               |
| Preview lifecycle         | Staging and preview releases passed; preview redeployment retained credentials; cleanup removed its namespace, database, and role                    |
| Failed rollout            | An intentionally unpublished frontend image produced ImagePullBackOff and a failed rollout check                                                     |
| Rollback                  | Both Application configurations were restored, HTTP checks passed, migrations did not rerun, and the schema version and test data remained unchanged |
| Scale up/down             | Staging reached two healthy backend replicas through the release tool, then returned to one after load testing                                       |

The isolated lifecycle and rollback checks used the existing `tools/deploy/tests/check_kind.py`. That test creates and removes its own resources. The persistent staging and sample preview were deployed afterward and left running.

## Load results

Requests went through a local port-forward to frontend Nginx, then the backend and PostgreSQL. Each cycle created an idea, read the list, and deleted that idea. Test data was removed successfully.

| Backend replicas | Concurrent cycles | Cycles | Requests | Seconds | Requests/sec | p95 request, ms | Failed requests |
| ---------------- | ----------------- | ------ | -------- | ------- | ------------ | --------------- | --------------- |
| 1                | 10                | 1,000  | 3,000    | 7.627   | 393.32       | 44.43           | 0               |
| 1                | 25                | 1,000  | 3,000    | 8.155   | 367.87       | 113.61          | 0               |
| 1                | 50                | 1,000  | 3,000    | 7.478   | 401.18       | 204.25          | 0               |
| 2                | 50                | 1,000  | 3,000    | 5.226   | 574.09       | 138.66          | 0               |
| 2                | 50                | 10,000 | 30,000   | 55.282  | 542.68       | 144.14          | 0               |

All 42,000 measured requests passed, with no failed cycles or cleanup failures. No latency threshold was configured. The longer run lasted about 55 seconds; these are short local measurements, not a soak test or a production capacity guarantee.

The controlled comparison at concurrency 50 improved from 401 to 574 requests/second when the backend went from one replica to two. Repeated runs and longer observation would be needed to establish a reliable capacity limit.

The [raw results](evidence/load-results.json) contain the test outputs. To repeat a run against staging:

```bash
IDEA_BOARD_BASE_URL=http://127.0.0.1:3002 LOAD_CYCLES=1000 LOAD_CONCURRENCY=50 \
  npm --prefix apps/frontend run test:load
```

For the scaling comparison, set `backend.replicas` to `2` in a copy of the recorded recommendation and release it with the same staging command in the kind guide. Repeat the load command, then release the original recommendation to return to one replica.

## Test setup

- One ARM64 kind node, Kubernetes `v1.33.1`, Argo CD `v3.6.1`, PostgreSQL `17`.
- Docker reported 16 CPUs and 40.95 GiB available memory. The machine also ran other containers.
- Staging and preview image/chart revision: `5ae00d82541190e313a06e14f39ddc94124455a8`.
- Backend: one Uvicorn process per pod, CPU request `100m`, memory request/limit `128Mi`/`256Mi`.
- Frontend: one replica, CPU request `50m`, memory request/limit `32Mi`/`128Mi`.
- PostgreSQL: CPU request `100m`, memory request/limit `64Mi`/`256Mi`, `max_connections = 100`.

The backend's measured pool configuration permits five pooled connections plus ten overflow connections per process. Two staging replicas can therefore open up to 30 connections. The original app, preview, migrations, and administration also use connections and must be included before raising replica limits. This is configuration arithmetic, not a measured database saturation point.

## AI recommendation and diagnosis

The assistant generated a [recommendation](evidence/recommendation.json) for this local setup during the verification session. The deployment tool validated it, generated a release plan, and used it to deploy the persistent staging and preview services.

After the failure test, the assistant generated a [diagnosis](evidence/diagnosis.json) from the [captured evidence](evidence/failed-rollout.json). The report command validated the schema, evidence references, and rollback eligibility. The recommendation did not execute a rollback; the isolated test explicitly invoked the rollback tool after confirming schema compatibility.

The integration test uses fixed recommendations so it can run independently of a model. This interactive AI session does not verify the GitHub Actions AI runner's authentication.

## Verification boundary

This run reused an existing cluster. The persistent PostgreSQL manifest passed a Kubernetes server-side dry run and matched the running deployment. A fresh-machine bootstrap was not exercised.

Metrics Server was unavailable, so per-pod CPU and memory under load were not measured. Cloud networking, managed database access, cloud secret access, and public load balancers were not exercised. The independent AWS and GCP stacks have validation and provider-mock tests, with no current public application URLs.
