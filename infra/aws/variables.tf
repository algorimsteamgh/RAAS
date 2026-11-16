variable "region" {
  description = "AWS Region. All candidate data stays in this Region."
  type        = string
  default     = "ap-southeast-1"
}

variable "environment" {
  description = "Environment name, used in resource names."
  type        = string
  default     = "prod"
}

variable "vpc_cidr" {
  description = "Address range of the RAAS VPC. Must be a /16."
  type        = string
  default     = "10.60.0.0/16"
}

variable "db_name" {
  description = "Name of the PostgreSQL database."
  type        = string
  default     = "raas"
}

variable "db_instance_class" {
  description = "RDS instance class."
  type        = string
  default     = "db.t4g.medium"
}

variable "db_allocated_storage" {
  description = "RDS storage in GB (gp3)."
  type        = number
  default     = 50
}

variable "db_multi_az" {
  description = "Run a standby database in the second Availability Zone."
  type        = bool
  default     = true
}

variable "db_backup_retention_days" {
  description = "Days of automated backups (point-in-time recovery)."
  type        = number
  default     = 35
}

variable "db_deletion_protection" {
  description = "Block deletion of the database. Set false only to tear the stack down."
  type        = bool
  default     = true
}

variable "aws_account_id" {
  description = "Quess Global's AWS account. Terraform refuses to run against any other account."
  type        = string
  default     = "007477962703"
}

# ---------------------------------------------------------------- application

variable "api_image_tag" {
  description = "Image tag (commit SHA) in ECR for the API and worker. Empty = no image yet, services run 0 tasks."
  type        = string
  default     = ""
}

variable "api_cpu" {
  type    = number
  default = 1024
}

variable "api_memory" {
  type    = number
  default = 2048
}

variable "api_min_tasks" {
  type    = number
  default = 2
}

variable "api_max_tasks" {
  type    = number
  default = 6
}

variable "cpu_architecture" {
  description = "X86_64 or ARM64 (Graviton) — must match the pushed image."
  type        = string
  default     = "X86_64"
}

variable "worker_command" {
  description = "Command for the SQS batch worker (entry point is part of the app code changes)."
  type        = list(string)
  default     = ["python", "-m", "backend.app.worker"]
}

variable "worker_desired_count" {
  description = "Worker tasks. Keep 0 until the worker entry point exists in the image."
  type        = number
  default     = 0
}

variable "migrate_command" {
  description = "Command for the one-off migration / data-load ECS task."
  type        = list(string)
  default     = ["python", "-m", "backend.app.db.migrate"]
}

variable "app_environment" {
  description = "Extra plain environment variables for the API and worker containers."
  type        = map(string)
  default     = {}
}

variable "log_retention_days" {
  type    = number
  default = 90
}

# ---------------------------------------------------------------- Bedrock

variable "bedrock_foundation_model_ids" {
  description = "In-region on-demand models the app may call (Converse API). Under evaluation: Nova Lite and Claude Haiku."
  type        = list(string)
  default = [
    "amazon.nova-lite-v1:0",
    "anthropic.claude-3-haiku-20240307-v1:0",
  ]
}

variable "bedrock_inference_profile_ids" {
  description = "Cross-region inference profiles (e.g. apac.amazon.nova-lite-v1:0). Leave empty unless decision D2 allows cross-region inference."
  type        = list(string)
  default     = []
}

# ---------------------------------------------------------------- edge and DNS

variable "domain_name" {
  type    = string
  default = "raashiring.com"
}

variable "hosted_zone_id" {
  description = "Existing Route 53 zone for domain_name. Empty = Terraform creates the zone."
  type        = string
  default     = ""
}

variable "enable_custom_domain" {
  description = "Create ACM certificates (DNS-validated) and attach raashiring.com to CloudFront. Turn on only after GoDaddy's name servers point at the Route 53 zone, or validation waits and times out."
  type        = bool
  default     = false
}

variable "point_dns_to_aws" {
  description = "Cut-over switch: apex and www alias records to CloudFront. Needs enable_custom_domain."
  type        = bool
  default     = false
}

variable "origin_subdomain" {
  description = "Hostname CloudFront uses to reach the ALB over HTTPS (origin.<domain>)."
  type        = string
  default     = "origin"
}

variable "waf_rate_limit" {
  description = "Requests per 5 minutes per IP before WAF blocks."
  type        = number
  default     = 2000
}

variable "cloudfront_price_class" {
  type    = string
  default = "PriceClass_200"
}

# ---------------------------------------------------------------- CI/CD

variable "github_repository" {
  description = "owner/name of the repository whose GitHub Actions may deploy."
  type        = string
  default     = "algorimsteamgh/raas"
}

variable "github_environment" {
  type    = string
  default = "production"
}

variable "create_github_oidc_provider" {
  description = "Set false if the account already has the token.actions.githubusercontent.com provider."
  type        = bool
  default     = true
}

# ---------------------------------------------------------------- operations

variable "alarm_email" {
  description = "Email subscribed to the alarm topic. Empty = no subscription."
  type        = string
  default     = ""
}

variable "enable_aws_backup" {
  type    = bool
  default = true
}

variable "backup_retention_days" {
  type    = number
  default = 90
}

variable "enable_account_security_services" {
  description = "CloudTrail, GuardDuty and Security Hub. Set false if the account (or its AWS Organization) already enables them."
  type        = bool
  default     = true
}

# ---------------------------------------------------------------- Liftproof (validation tool)

variable "liftproof_security_group_id" {
  description = "Security group of the Liftproof instance (after its stack is installed). Opens RDS 5432 to it."
  type        = string
  default     = ""
}

variable "liftproof_instance_role_name" {
  description = "IAM role of the Liftproof instance, e.g. liftproof-raas-instance. Grants read access to the CV bucket."
  type        = string
  default     = ""
}

variable "flow_log_retention_days" {
  description = "Days to keep VPC flow logs."
  type        = number
  default     = 30
}
