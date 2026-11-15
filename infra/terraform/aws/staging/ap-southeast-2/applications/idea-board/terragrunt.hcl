include "root" {
  path = find_in_parent_folders("root.hcl")
}

dependencies {
  paths = ["../../networking", "../../cluster", "../../cluster-core-services"]
}

inputs = {
  database_backup_retention_days = 0
}
