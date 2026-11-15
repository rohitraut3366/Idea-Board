resource "google_sql_database_instance" "this" {
  name                = "${var.name}-postgres"
  region              = var.region
  database_version    = "POSTGRES_17"
  deletion_protection = var.deletion_protection
  settings {
    tier                        = var.tier
    edition                     = "ENTERPRISE"
    availability_type           = var.regional ? "REGIONAL" : "ZONAL"
    disk_type                   = "PD_SSD"
    disk_size                   = var.storage_gb
    disk_autoresize             = true
    deletion_protection_enabled = var.deletion_protection
    ip_configuration {
      ipv4_enabled    = false
      private_network = var.network_id
      ssl_mode        = "ENCRYPTED_ONLY"
    }
    backup_configuration {
      enabled                        = true
      point_in_time_recovery_enabled = true
      start_time                     = "02:00"
      backup_retention_settings {
        retained_backups = 7
      }
    }
  }
}

resource "google_sql_database" "this" {
  name     = "idea_board"
  instance = google_sql_database_instance.this.name
}

resource "google_sql_user" "this" {
  name     = "idea_board_admin"
  instance = google_sql_database_instance.this.name
  password = var.password
}

resource "google_secret_manager_secret" "database" {
  secret_id = "${var.name}-postgres"
  replication {
    auto {}
  }
}

resource "google_secret_manager_secret_version" "database" {
  secret = google_secret_manager_secret.database.id
  secret_data = jsonencode({
    username = google_sql_user.this.name
    password = var.password
  })
}
