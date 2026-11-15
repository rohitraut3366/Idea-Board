mock_provider "helm" {}

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
}
