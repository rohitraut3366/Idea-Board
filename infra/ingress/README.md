# Ingress setup

Ingress provides one public address for the web app and API. The frontend chart declares the routes; the cloud's controller creates the load balancer, routing rules, health checks, and backend registrations.

```text
Browser → public load balancer → /api/* → backend Service → API pods
                             → /*      → frontend Service → frontend pods
```

React renders in the browser and makes separate page and API requests to the same origin. Cloud API requests go directly to the backend through the load balancer. Local Compose traffic still uses the Nginx `/api/` proxy.

## Ownership and apply order

1. Apply `infra/terraform/aws` or `infra/terraform/gcp` to create the network, cluster, and database.
2. Set up the controller as described below. AWS has a separate Terraform root for controller IAM and Pod Identity, followed by an Argo installation. GCP uses its built-in controller.
3. Release the application through GitHub Actions and Argo CD. The frontend chart creates an Ingress referencing both Services. The workflow waits for its address and verifies the page and API before reporting success.

Terraform does **not** manage ALBs, target groups, Google load-balancer resources, or individual pod registrations. There are no manually configured target-group ARNs, NodePorts, or preallocated public URL inputs. The controller reconciles those resources from Kubernetes configuration and removes them when the Ingress is deleted.

| Cloud | Controller                                      | Kubernetes configuration                                                              |
| ----- | ----------------------------------------------- | ------------------------------------------------------------------------------------- |
| AWS   | AWS Load Balancer Controller, installed by Argo | `ingressClassName: alb`, public ALB, IP targets, per-Service health paths             |
| GCP   | Built-in GKE Ingress controller                 | `kubernetes.io/ingress.class: gce`, NEGs for pod targets, BackendConfig health checks |

Both use ClusterIP Services and route the `/api` path prefix to backend port 8000; `/` defaults to frontend port 80. Kubernetes Prefix matching includes `/api` and `/api/...`, while `/apix` does not match. Pods and databases remain private.

## AWS: post-cluster setup

The [aws directory](aws) is a Terraform root with separate state from the cluster project. It creates the Pod Identity agent add-on, a controller IAM role/policy, and the association with `kube-system/aws-load-balancer-controller`. It exports an Argo Application for the pinned controller chart.

Use one controller setup per cluster; staging and its previews share that installation. Production uses its own cluster/setup. If the agent or controller is already managed elsewhere, establish one owner rather than applying a second installation.

From the repository root:

```bash
cp infra/ingress/aws/terraform.tfvars.example infra/ingress/aws/terraform.tfvars
cp infra/ingress/aws/backend.hcl.example infra/ingress/aws/backend.hcl
```

Set the existing cluster name, AWS region, and VPC ID. The cluster project exports `cluster_name` and `vpc_id`; a previously applied stack may need a normal reviewed apply to record the new output. Configure the backend with an existing state bucket and a **different state key** from the cluster project. The example uses `idea-board/ingress/staging/terraform.tfstate`.

```bash
terraform -chdir=infra/ingress/aws init -backend-config=backend.hcl
terraform -chdir=infra/ingress/aws validate
terraform -chdir=infra/ingress/aws plan -out=controller.tfplan
# Review IAM and add-on changes before applying.
terraform -chdir=infra/ingress/aws apply controller.tfplan
```

After Argo CD is installed, apply the generated controller Application to the intended EKS context:

```bash
terraform -chdir=infra/ingress/aws output -raw controller_application > /tmp/idea-board-ingress-controller.yaml
kubectl --context YOUR_EKS_CONTEXT apply -f /tmp/idea-board-ingress-controller.yaml
kubectl --context YOUR_EKS_CONTEXT --namespace argocd get application aws-load-balancer-controller
kubectl --context YOUR_EKS_CONTEXT --namespace kube-system rollout status deployment/aws-load-balancer-controller --timeout=5m
```

Argo may need time to create the Deployment; if `rollout status` initially reports NotFound, inspect the Application and retry after sync starts. Wait for the Application to be Synced and Healthy before releasing the app. This platform Application uses Argo's `default` project because it installs CRDs and cluster RBAC; applying it requires platform administrator access. Application releases use their own restricted namespace projects.

The controller receives AWS credentials through Pod Identity. Its trust checks cluster name, namespace, and service account. There are no access keys or service-account IAM annotations. Existing worker roles use `AmazonEKSWorkerNodePolicy`, which permits Pod Identity authentication.

The chart/controller and vendored [official IAM policy](https://github.com/kubernetes-sigs/aws-load-balancer-controller/blob/v3.6.3/docs/install/iam_policy.json) are pinned to **3.6.3**. Upgrade them together. The controller uses subnet role tags already created by the network module to discover public subnets, and manages ALB security groups and worker access for its pod targets.

Helm generates webhook certificates during rendering. The Application preserves installed Secret data and webhook CA bundles to avoid replacing them on every sync. Rotate those certificates as one explicit maintenance operation before expiry, updating the Secret and CA bundles together.

## GCP: built-in controller

See the [GCP setup notes](gcp/README.md). The cluster module explicitly enables GKE HTTP load balancing. No extra controller chart, IAM role, or post-cluster Terraform state is needed for GCP.

Each chart declares a BackendConfig with an explicit pod health path and port: backend `/health` on 8000 and frontend `/` on 8080. Service annotations enable GKE-managed network endpoint groups (NEGs) and reference the corresponding BackendConfig. GKE registers pod addresses and manages load-balancer health checks and traffic access. Terraform does not precreate NEGs or track pod IPs.

## Releases, previews, and access

The normal Deploy workflow supplies the provider-specific chart settings. It waits for the AWS controller when applicable, submits backend before frontend, and discovers the public hostname/IP from `Ingress/frontend` in the target namespace. A page-only response cannot pass verification: `/api/ideas` must return a successful JSON array too.

The same configuration works for staging, production, and PR previews. Each namespace gets its own Ingress and public load balancer. Closing a PR deletes its Applications, which lets the controller remove that preview's load balancer and registrations. No Terraform apply is needed per preview. Separate load balancers incur charges; this setup does not share one hostname-based load balancer across previews.

Routing currently serves HTTP on port 80. DNS, certificates/HTTPS, WAF, and rate limiting need additional configuration. The app permits anonymous idea creation and deletion. Local kind does not install a cloud controller or create an Ingress; use its existing frontend port-forward.

## Validation and cleanup

CI validates and mock-plans the AWS controller root, checks the GKE add-on configuration, and renders both charts for each cloud/environment. Tests check path routing, health configuration, namespace permissions, and public page/API verification. Provider mocks do not prove IAM acceptance, pod registration, or public connectivity. Live cloud apply, target health, HTTP access, and cleanup remain required verification.

To remove an environment, delete its Argo application resources and wait for the Ingress and controller-managed load balancer to disappear. Keep the controller, its IAM role, and the cluster available until cleanup completes. If finalizers block deletion, inspect controller logs and permissions before removing anything manually. Destroy the AWS controller setup after its Ingress resources are gone, then destroy the cluster project. Confirm cloud load balancers and associated billable resources have actually been removed.
