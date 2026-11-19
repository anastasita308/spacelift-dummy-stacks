terraform {
  required_version = ">= 1.4.0"
}

resource "terraform_data" "test" {
  input = "KEDA autoscaling test"
}

output "result" {
  value = terraform_data.test.output
}