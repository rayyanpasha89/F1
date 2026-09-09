terraform {

  required_version = ">= 1.13, < 2.0"
  required_providers {

    aws = {
      source = "hashicorp/aws", version = "~> 6.14"
    }


  }


}

provider "aws" {

  profile             = "default"
  region              = "eu-north-1"
  allowed_account_ids = ["148356747273"]
  default_tags {
    tags = {
      Project = "F1-Race-Strategist", Environment = "dev"
    }

  }


}

locals {
  name = "f1-race-strategist-dev"
}

variable "image_tag" {
  type    = string
  default = "bootstrap"

}

variable "desired_count" {
  type    = number
  default = 0
  validation {
    condition     = contains([0, 1], var.desired_count)
    error_message = "Development deployment supports zero or one task."

  }


}

data "aws_caller_identity" "current" {

}

data "aws_availability_zones" "available" {
  state = "available"
}

