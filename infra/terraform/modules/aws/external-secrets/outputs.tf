output "values_file_path" {
  description = "Generated External Secrets values file in Git."
  value       = module.values_file.file_path
}

output "helm_values" {
  description = "Generated service-account settings used by the External Secrets chart."
  value       = local.helm_values
}
