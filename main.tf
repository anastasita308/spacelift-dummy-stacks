terraform {
  required_providers {
    spacelift = {
      source = "spacelift-io/spacelift"
    }
  }
}

provider "spacelift" {}

variable "stack_count" {
  type    = number
  default = 50
}

variable "repository" {
  type = string
}

variable "worker_pool_id" {
  type = string
}

variable "github_enterprise_id" {
  type = string
}

resource "spacelift_stack" "autoscaling_test" {
  for_each = toset([
    for i in range(var.stack_count) :
    format("autoscaling-test-%03d", i + 1)
  ])

  name        = each.value
  description = "KEDA worker pool autoscaling test"

  repository   = var.repository
  branch       = "main"
  project_root = "workload"

  worker_pool_id = var.worker_pool_id

  github_enterprise {
    id        = var.github_enterprise_id
    namespace = "anastasita308"
  }

  autodeploy = false

  labels = ["autoscaling-test"]

  before_plan = ["sleep 120"]
}