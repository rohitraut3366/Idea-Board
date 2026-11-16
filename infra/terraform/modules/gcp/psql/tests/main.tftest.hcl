mock_provider "google" {
  override_during = plan

  mock_resource "google_sql_database_instance" {
    defaults = { private_ip_address = "10.30.0.2" }
  }
}

mock_provider "random" {
  override_during = plan

  mock_resource "random_password" {
    defaults = { result = "test+password:?%&" }
  }
}

variables {
  name       = "idea-board-test"
  region     = "us-central1"
  network_id = "projects/test-project/global/networks/test"
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
    condition     = random_password.database.length == 32 && random_password.database.special && google_sql_user.this.password == random_password.database.result
    error_message = "Generate the SQL user's password with the Random provider."
  }

  assert {
    condition     = jsondecode(google_secret_manager_secret_version.database.secret_data).DATABASE_URL == "postgresql+psycopg://idea_board_admin:test%2Bpassword%3A%3F%25%26@10.30.0.2:5432/idea_board?sslmode=require"
    error_message = "Store the complete TLS connection URL with encoded credentials."
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
