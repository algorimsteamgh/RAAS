output "vpc_id" {
  value = aws_vpc.main.id
}

output "app_subnet_ids" {
  description = "Private subnets for ECS tasks and Liftproof."
  value       = aws_subnet.app[*].id
}

output "app_route_table_id" {
  value = aws_route_table.app.id
}

output "data_subnet_cidrs" {
  description = "The two database subnets (Liftproof Database1Cidr and Database2Cidr)."
  value       = aws_subnet.data[*].cidr_block
}

output "public_subnet_ids" {
  value = aws_subnet.public[*].id
}

output "app_security_group_id" {
  value = aws_security_group.app.id
}

output "db_security_group_id" {
  value = aws_security_group.db.id
}

output "db_endpoint" {
  value = aws_db_instance.main.address
}

output "db_name" {
  value = aws_db_instance.main.db_name
}

output "db_master_secret_arn" {
  description = "Secrets Manager secret holding the master login, created by RDS."
  value       = aws_db_instance.main.master_user_secret[0].secret_arn
}

output "cv_bucket" {
  value = aws_s3_bucket.cvs.bucket
}

output "data_kms_key_arn" {
  value = aws_kms_key.data.arn
}

output "nat_public_ip" {
  description = "Outbound IP of the app tier (for allow-lists elsewhere)."
  value       = aws_eip.nat.public_ip
}

# ── Application and edge ────────────────────────────────────────────────────

output "ecr_repository_url" {
  value = aws_ecr_repository.api.repository_url
}

output "ecs_cluster_name" {
  value = aws_ecs_cluster.main.name
}

output "migrate_task_definition" {
  description = "One-off ECS task for schema migrations and the SQLite-to-RDS load."
  value       = aws_ecs_task_definition.migrate.family
}

output "batch_queue_url" {
  value = aws_sqs_queue.batch.url
}

output "frontend_bucket" {
  value = aws_s3_bucket.frontend.bucket
}

output "cloudfront_distribution_id" {
  value = aws_cloudfront_distribution.main.id
}

output "cloudfront_domain_name" {
  description = "Test the site here before the DNS switch."
  value       = aws_cloudfront_distribution.main.domain_name
}

output "site_username" {
  value = var.site_password_enabled ? var.site_username : null
}

output "site_password" {
  description = "Shared site password (terraform output -raw site_password). Rotate: terraform apply -replace=random_password.site"
  value       = var.site_password_enabled ? random_password.site.result : null
  sensitive   = true
}

output "alb_dns_name" {
  value = aws_lb.main.dns_name
}

output "route53_zone_id" {
  value = local.zone_id
}

output "route53_name_servers" {
  description = "Set these as the name servers for raashiring.com at GoDaddy (only when Terraform created the zone)."
  value       = var.hosted_zone_id == "" ? aws_route53_zone.main[0].name_servers : []
}

output "github_deploy_role_arn" {
  description = "Put in the GitHub 'production' environment as AWS_ROLE_ARN."
  value       = aws_iam_role.github_deploy.arn
}

output "alarm_topic_arn" {
  value = aws_sns_topic.alarms.arn
}

# ── Liftproof (Part C2) ─────────────────────────────────────────────────────

output "liftproof_create_stack_parameters" {
  description = "Paste after --parameters in the Liftproof Part C2 create-stack command."
  value = join(" ", [
    "ParameterKey=DeploymentName,ParameterValue=raas",
    "ParameterKey=VpcId,ParameterValue=${aws_vpc.main.id}",
    "ParameterKey=SubnetId,ParameterValue=${aws_subnet.app[0].id}",
    "ParameterKey=CreateVpcEndpoints,ParameterValue=false",
    "ParameterKey=PrivateRouteTableIds,ParameterValue=${aws_route_table.app.id}",
    "ParameterKey=Database1Cidr,ParameterValue=${aws_subnet.data[0].cidr_block}",
    "ParameterKey=Database1Port,ParameterValue=5432",
    "ParameterKey=Database2Cidr,ParameterValue=${aws_subnet.data[1].cidr_block}",
    "ParameterKey=Database2Port,ParameterValue=5432",
    "ParameterKey=ApplicationCidrs,ParameterValue=0.0.0.0/0",
    "ParameterKey=SecretArns,ParameterValue='arn:${data.aws_partition.current.partition}:secretsmanager:${var.region}:${data.aws_caller_identity.current.account_id}:secret:liftproof/*'",
    "ParameterKey=SecretKmsKeyArns,ParameterValue=${aws_kms_key.data.arn}",
  ])
}
