locals {
  helm_values = {
    serviceAccount = {
      name = "external-secrets"
      annotations = {
        "iam.gke.io/gcp-service-account" = google_service_account.this.email
      }
    }
  }
}

resource "google_service_account" "this" {
  project      = var.project_id
  account_id   = "${var.name}-eso"
  display_name = "External Secrets Operator"
}

resource "google_service_account_iam_member" "workload_identity" {
  service_account_id = google_service_account.this.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "serviceAccount:${var.project_id}.svc.id.goog[external-secrets/external-secrets]"
}

resource "google_project_iam_member" "secret_access" {
  project = var.project_id
  role    = "roles/secretmanager.secretAccessor"
  member  = "serviceAccount:${google_service_account.this.email}"
}

module "values_file" {
  source       = "../../github/helm-values"
  chart_path   = "charts/external-secrets"
  cloud        = "gcp"
  cluster_name = var.cluster_name
  values       = { external-secrets = local.helm_values }
  depends_on   = [google_service_account_iam_member.workload_identity, google_project_iam_member.secret_access]
}
