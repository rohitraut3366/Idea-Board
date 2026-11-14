# GitOps

Argo CD manages the backend and frontend as separate Applications in `kind-idea-board`. Each Application renders its Helm chart using the values in `kind/` and watches `rohit-e2e-implementation-plan`. PostgreSQL, its persistent volume, and the database Secret are provisioned separately.

## Install Argo CD

The upstream installation is pinned to v3.6.1. The local overlay reuses cached versioned images with `IfNotPresent` to avoid repeated registry pulls on kind:

```bash
kubectl --context kind-idea-board create namespace argocd
kubectl --context kind-idea-board --namespace argocd apply --server-side -k gitops/argocd
kubectl --context kind-idea-board --namespace argocd rollout status deployment/argocd-server --timeout=3m
```

For a private repository, provision an Argo CD repository Secret with a read-only deploy key first. Its URL must match `git@github.com:rohitraut3366/Idea-Board.git`. Keep the private key outside Git. Argo CD's upstream SSH known-hosts configuration includes GitHub's host keys.

## Connect the services

Before applying the Applications, the `idea-board` namespace must have a ready PostgreSQL instance and a Secret named `idea-board-database` containing `IDEA_BOARD_DATABASE_URL`. The application images named in `kind/*-values.yaml` must be available on the kind nodes.

```bash
kubectl --context kind-idea-board apply -k gitops/kind
kubectl --context kind-idea-board --namespace argocd get applications
```

The AppProject permits only this repository, the `idea-board` namespace, and Deployments, Services, and Jobs. It cannot manage cluster resources or database Secrets and storage.

Argo CD adopts the existing backend and frontend resources. Use Git changes for subsequent releases rather than running Helm upgrades against those workloads. The old Helm release records remain as history.

## Changes and recovery

Edit `kind/backend-values.yaml` or `kind/frontend-values.yaml`, commit, and push to the watched branch. Argo CD automatically syncs Git changes, corrects drift, and prunes removed application resources. After merging this branch, update both Applications' `targetRevision` before applying them again.

Backend sync runs the migration Job as a `PreSync` hook. A failed migration stops that sync before the Deployment changes. Inspect the Application status and the retained migration Job logs:

```bash
kubectl --context kind-idea-board --namespace argocd get application backend -o yaml
kubectl --context kind-idea-board --namespace idea-board logs job/backend-migrate
```

To restore a prior configuration, revert the faulty commit and push the revert. Argo CD reconciles the reverted configuration. This restores application configuration; it does not reverse database migrations, so migrations must remain compatible with the previous application version.

CI runs backend smoke checks for health and create/read/delete, and frontend checks for the page and API proxy. Argo CD skips those Helm test Pods during sync.

## Local access

```bash
kubectl --context kind-idea-board --namespace idea-board port-forward service/frontend 3001:80
kubectl --context kind-idea-board --namespace argocd port-forward service/argocd-server 8080:443
```

The web app is at `http://localhost:3001`. Argo CD is at `https://localhost:8080` with its local self-signed certificate. The initial username is `admin`; retrieve its password locally:

```bash
kubectl --context kind-idea-board --namespace argocd get secret argocd-initial-admin-secret \
  -o jsonpath='{.data.password}' | base64 --decode
```

The cluster and services remain running until you explicitly stop them.
