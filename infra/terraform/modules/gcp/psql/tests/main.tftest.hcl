mock_provider "google" {
  override_during = plan

}

variables {
  name       = "idea-board-test"
  region     = "us-central1"
  network_id = "projects/test-project/global/networks/test"
  password   = "mock-test-password-only"
}

run "configuration" {
  command = plan

  assert {
    condition     = !google_sql_database_instance.this.settings[0].ip_configuration[0].ipv4_enabled && google_sql_database_instance.this.settings[0].ip_configuration[0].private_network == var.network_id
    error_message = "Cloud SQL must have only private VPC connectivity."
  }

  assert {
    condition     = google_sql_database_instance.this.settings[0].ip_configuration[0].ssl_mode == "ENCRYPTED_ONLY"
    error_message = "Database connections must use TLS."
  }

  assert {
    condition     = google_sql_database_instance.this.settings[0].backup_configuration[0].enabled && google_sql_database_instance.this.settings[0].backup_configuration[0].point_in_time_recovery_enabled && google_sql_database_instance.this.deletion_protection && google_sql_database_instance.this.settings[0].deletion_protection_enabled
    error_message = "Keep backups, point-in-time recovery, and deletion protection."
  }

  assert {
    condition     = jsondecode(google_secret_manager_secret_version.database.secret_data).password == var.password && jsondecode(google_secret_manager_secret_version.database.secret_data).username == google_sql_user.this.name
    error_message = "The stored credentials must match the SQL user."
  }
}

run "larger_database" {
  command = plan
  variables {
    tier       = "db-custom-2-7680"
    storage_gb = 100
    regional   = true
  }
  assert {
    condition     = google_sql_database_instance.this.settings[0].availability_type == "REGIONAL" && google_sql_database_instance.this.settings[0].disk_size == 100 && google_sql_database_instance.this.settings[0].tier == "db-custom-2-7680"
    error_message = "Database availability and capacity must follow the configured values."
  }
}
