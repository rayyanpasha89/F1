terraform {
  required_version = ">= 1.13, < 2.0"
  required_providers {
    aws = { source = "hashicorp/aws", version = "= 6.63.0" }
  }
}
provider "aws" {
  profile             = "default"
  region              = "eu-north-1"
  allowed_account_ids = ["148356747273"]
  default_tags {
    tags = { Project = "F1-Race-Strategist", Environment = "dev" }
  }
}
resource "aws_lightsail_container_service" "app" {
  name  = "f1-strategist-demo"
  power = "small"
  scale = 1
  private_registry_access {
    ecr_image_puller_role {
      is_active = true
    }
  }
}
resource "aws_ecr_repository_policy" "lightsail" {
  repository = "f1-race-strategist-dev"
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid       = "LightsailProjectPull"
      Effect    = "Allow"
      Principal = { AWS = aws_lightsail_container_service.app.private_registry_access[0].ecr_image_puller_role[0].principal_arn }
      Action    = ["ecr:BatchGetImage", "ecr:GetDownloadUrlForLayer"]
    }]
  })
}
# Native aws_lightsail_database requires a password in Terraform state.
# CloudFormation permits Lightsail to generate and retain it instead.
resource "aws_cloudformation_stack" "database" {
  name             = "f1-strategist-demo-database"
  disable_rollback = true
  template_body = jsonencode({
    AWSTemplateFormatVersion = "2010-09-09"
    Resources = {
      Database = {
        Type                = "AWS::Lightsail::Database"
        DeletionPolicy      = "Retain"
        UpdateReplacePolicy = "Retain"
        Properties = {
          RelationalDatabaseName        = "f1-strategist-demo-db"
          RelationalDatabaseBlueprintId = "postgres_16"
          RelationalDatabaseBundleId    = "micro_2_0"
          MasterDatabaseName            = "f1"
          MasterUsername                = "f1admin"
          PubliclyAccessible            = false
          Tags                          = [{ Key = "Project", Value = "F1-Race-Strategist" }, { Key = "Environment", Value = "dev" }]
        }
      }
    }
  })
  lifecycle {
    prevent_destroy = true
  }
}
output "url" { value = aws_lightsail_container_service.app.url }
output "service_name" { value = aws_lightsail_container_service.app.name }
output "database_name" { value = "f1-strategist-demo-db" }
