terraform {
  required_version = ">= 1.10"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.80"
    }
  }

  # State lives in an S3 bucket in the same AWS account. The bucket is created
  # once by hand (see README.md) and passed in at init time:
  #   terraform init -backend-config="bucket=raas-tfstate-ACCOUNT-ap-southeast-1"
  backend "s3" {
    key          = "raas/production/terraform.tfstate"
    region       = "ap-southeast-1"
    encrypt      = true
    use_lockfile = true
  }
}

provider "aws" {
  region = var.region

  default_tags {
    tags = {
      Application = "RAASHiring"
      Environment = var.environment
      ManagedBy   = "Terraform"
    }
  }
}

data "aws_caller_identity" "current" {}

data "aws_availability_zones" "available" {
  state = "available"
}

locals {
  name = "raas-${var.environment}"
  azs  = slice(data.aws_availability_zones.available.names, 0, 2)
}
