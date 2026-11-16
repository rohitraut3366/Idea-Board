output "file_path" {
  value = github_repository_file.this.file
}
output "file_content" {
  description = "Generated non-secret Helm configuration."
  value       = github_repository_file.this.content
}
