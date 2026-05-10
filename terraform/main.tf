terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }

  backend "s3" {
    bucket         = "moon-tfstate-489922706493"
    key            = "moon/terraform.tfstate"
    region         = "us-east-1" # state bucket stays in us-east-1
    use_lockfile = true
    encrypt      = true
  }
}

provider "aws" {
  region = var.aws_region
}

data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

locals {
  tags = {
    Project   = var.app_name
    ManagedBy = "terraform"
  }
}
