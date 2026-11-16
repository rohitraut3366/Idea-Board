mock_provider "google" {
  override_during = plan
  mock_resource "google_service_account" {
    defaults = {
      name  = "projects/test-project/serviceAccounts/idea-board-test-eso@test-project.iam.gserviceaccount.com"
      email = "idea-board-test-eso@test-project.iam.gserviceaccount.com"
    }
  }
}
mock_provider "github" {}

variables {
  name         = "idea-board-test"
  cluster_name = "idea-board-test"
  project_id   = "test-project"
}

run "operator_workload_identity" {
  command = plan
  assert {
    condition     = google_service_account_iam_member.workload_identity.service_account_id == google_service_account.this.name && google_service_account_iam_member.workload_identity.role == "roles/iam.workloadIdentityUser" && google_service_account_iam_member.workload_identity.member == "serviceAccount:test-project.svc.id.goog[external-secrets/external-secrets]"
    error_message = "Bind the operator's Kubernetes service account to its Google service account."
  }
  assert {
    condition     = google_project_iam_member.secret_access.project == var.project_id && google_project_iam_member.secret_access.role == "roles/secretmanager.secretAccessor" && google_project_iam_member.secret_access.member == "serviceAccount:${google_service_account.this.email}"
    error_message = "Give the operator read access to project secrets."
  }
  assert {
    condition     = output.helm_values.serviceAccount.name == "external-secrets" && output.helm_values.serviceAccount.annotations["iam.gke.io/gcp-service-account"] == google_service_account.this.email && output.values_file_path == "charts/external-secrets/values/gcp/idea-board-test/values-terraform.yaml"
    error_message = "Publish the created identity annotation to the correct cluster's Helm values."
  }
}
