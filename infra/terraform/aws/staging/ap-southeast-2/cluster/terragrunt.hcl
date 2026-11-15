include "root" {
  path = find_in_parent_folders("root.hcl")
}

dependencies {
  paths = ["../networking"]
}

inputs = {
  kubernetes_version = "1.35"
  node_instance_type = "c7i-flex.large"
  node_count         = 2
}
