terraform {
  required_version = ">= 1.10"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.80"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
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

locals {
  default_tags = {
    Application = "RAASHiring"
    Environment = var.environment
    ManagedBy   = "Terraform"
  }
}

provider "aws" {
  region              = var.region
  allowed_account_ids = [var.aws_account_id]

  default_tags {
    tags = local.default_tags
  }
}

# CloudFront needs its viewer certificate and WAF web ACL in us-east-1. Only
# those two edge objects live there; no candidate data is stored outside
# ap-southeast-1.
provider "aws" {
  alias               = "us_east_1"
  region              = "us-east-1"
  allowed_account_ids = [var.aws_account_id]

  default_tags {
    tags = local.default_tags
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
