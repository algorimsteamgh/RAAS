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
