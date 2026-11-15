locals {
  configured_project = get_env("GOOGLE_CLOUD_PROJECT", "")
  inputs = {
    name       = "idea-board-staging"
    project_id = local.configured_project != "" ? local.configured_project : run_cmd("--terragrunt-quiet", "gcloud", "config", "get-value", "project")
  }
}
