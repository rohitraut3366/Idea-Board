# Public routing

Ingress gives the web app and API one public address. The frontend chart declares the routes. The cloud controller creates the load balancer and connects it to the app's pods.

```text
Browser → public load balancer → /api/* → backend Service → API pods
                             → /*      → frontend Service → frontend pods
```

## Set up the controllers

Follow the [Terraform guide](../terraform/README.md) to configure and apply `networking`, `cluster`, `cluster-core-services`, and `applications/idea-board`, in order.

| Cloud | Controller                         | Installed by                                            |
| ----- | ---------------------------------- | ------------------------------------------------------- |
| AWS   | AWS Load Balancer Controller       | Terraform `cluster-core-services` project, through Helm |
| GCP   | GKE HTTP load-balancing controller | Terraform `cluster` project, through the GKE addon      |

Core services install Argo CD on both clouds. On AWS, the same project creates the controller IAM role, Pod Identity agent, and service-account association, then installs the controller chart. Its Helm release waits for readiness.

One controller installation serves a cluster, including its staging and preview namespaces. Production has its own cluster and core services.

## Release the application

1. Configure GitHub Actions using the [deployment instructions](../../README.md#3-configure-github-actions).
2. Run the Deploy workflow for the cloud and environment.
3. The workflow checks the AWS controller when applicable, then submits the backend and frontend Applications to Argo CD.
4. The frontend chart creates an Ingress pointing to both Services. The controller creates the public load balancer.
5. The workflow waits for an address and successful page and API responses, then reports the URL.

Terraform manages the platform installation. Argo CD manages the application charts. The cloud controller manages load balancers, routing rules, health checks, and pod registrations.

## Routes and health checks

| Cloud | Routing                                                | Health checks                                                        |
| ----- | ------------------------------------------------------ | -------------------------------------------------------------------- |
| AWS   | Public ALB, `alb` ingress class, IP targets            | Service annotations select backend `/health` and frontend `/`        |
| GCP   | `gce` Ingress, network endpoint groups for pod targets | Each chart creates a BackendConfig with the health path and pod port |

Both use ClusterIP Services. The `/api` path prefix reaches backend port 8000; `/` reaches frontend port 80. Kubernetes Prefix matching includes `/api` and `/api/...`. Pods and databases use private addresses.

For GCP inspection commands, see the [GKE notes](gcp/README.md).

## Previews and access

Staging, production, and each PR preview have their own namespace and Ingress. Each Ingress creates a public load balancer. Closing a PR removes its Applications, Ingress, and associated cloud resources. Previews share staging's cluster and database server.

Public routing currently serves HTTP on port 80. HTTPS requires DNS and certificate configuration. Local kind uses Traefik ingress; follow the [kind guide](../../gitops/README.md). Compose routes `/api/` requests through Nginx.

## Check and remove

CI renders charts for both clouds and checks routing, health settings, namespace permissions, and public-response validation. The Terraform jobs validate and mock-test the controller module and core-services projects. Live cloud routing and cleanup remain to be verified.

Inspect an environment's Ingress:

```bash
kubectl --context YOUR_CONTEXT --namespace YOUR_NAMESPACE get ingress frontend
kubectl --context YOUR_CONTEXT --namespace YOUR_NAMESPACE describe ingress frontend
```

Before destroying infrastructure, remove the app's Argo CD Applications and wait for their Ingress resources and load balancers to disappear. Keep the controller, its IAM role, and the cluster running until cleanup finishes. Then follow the [Terraform teardown order](../terraform/README.md#teardown).
