mock_provider "helm" {}

variables {
  gitops_revision = "test-revision"
  external_secrets_values = {
    serviceAccount = { annotations = { "eks.amazonaws.com/role-arn" = "arn:aws:iam::123456789012:role/external-secrets" } }
  }
}

run "configuration" {
  command = plan
  assert {
    condition     = helm_release.this.namespace == "argocd" && helm_release.this.wait && helm_release.this.atomic
    error_message = "Install Argo CD into its namespace and wait for a healthy release."
  }
  assert {
    condition     = yamldecode(helm_release.this.values[0]).server.service.type == "ClusterIP"
    error_message = "Argo CD should remain private."
  }
  assert {
    condition     = helm_release.core_services.namespace == "argocd" && yamldecode(helm_release.core_services.values[0]).targetRevision == "test-revision"
    error_message = "Bootstrap the root Application in Argo CD using the requested Git revision."
  }
  assert {
    condition     = yamldecode(helm_release.core_services.values[0]).externalSecrets.serviceAccount.annotations["eks.amazonaws.com/role-arn"] == "arn:aws:iam::123456789012:role/external-secrets"
    error_message = "Pass operator IAM annotations to the root Application."
  }
}
