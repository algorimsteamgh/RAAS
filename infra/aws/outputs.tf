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
