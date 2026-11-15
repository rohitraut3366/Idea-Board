# GKE Ingress

GKE provides the Ingress controller as the HTTP load-balancing add-on. The cluster module explicitly enables it, so this directory needs no extra controller installation or Terraform state.

After cluster creation, confirm the add-on is enabled:

```bash
gcloud container clusters describe YOUR_CLUSTER \
  --region YOUR_REGION --project YOUR_PROJECT \
  --format='value(addonsConfig.httpLoadBalancing.disabled)'
```

The value must not be `true`. Release the app with `cloud=gcp`. The frontend chart creates an Ingress using the `kubernetes.io/ingress.class: gce` annotation. Both Services enable container-native load balancing through GKE network endpoint groups; each chart provides its own BackendConfig health check. GKE owns the public load balancer, URL routing, backend health, and pod registration.

Inspect the target namespace:

```bash
kubectl --context YOUR_GKE_CONTEXT --namespace YOUR_NAMESPACE get ingress frontend
kubectl --context YOUR_GKE_CONTEXT --namespace YOUR_NAMESPACE describe ingress frontend
kubectl --context YOUR_GKE_CONTEXT --namespace YOUR_NAMESPACE get backendconfigs
```

Provisioning takes time. The workflow waits for an Ingress IP and successful page/API responses before reporting a working URL. See the [ingress guide](../README.md) for the shared routing, preview behavior, limitations, and cleanup order.
