mock_provider "aws" {
  mock_data "aws_availability_zones" {
    defaults = { names = ["ap-southeast-1a", "ap-southeast-1b", "ap-southeast-1c"] }
  }
  mock_data "aws_caller_identity" {
    defaults = { account_id = "007477962703" }
  }
  mock_data "aws_partition" {
    defaults = { partition = "aws" }
  }
  mock_data "aws_iam_policy_document" {
    defaults = { json = "{}" }
  }
  mock_data "aws_ec2_managed_prefix_list" {
    defaults = { id = "pl-123" }
  }
  mock_resource "aws_db_instance" {
    defaults = { master_user_secret = [{ secret_arn = "arn:aws:secretsmanager:ap-southeast-1:007477962703:secret:rds-x", kms_key_id = "k", secret_status = "active" }] }
  }
  mock_resource "aws_lb" { defaults = { arn = "arn:aws:elasticloadbalancing:ap-southeast-1:007477962703:loadbalancer/app/x/1", arn_suffix = "app/x/1" } }
  mock_resource "aws_lb_listener" { defaults = { arn = "arn:aws:elasticloadbalancing:ap-southeast-1:007477962703:listener/app/x/1/2" } }
  mock_resource "aws_lb_target_group" { defaults = { arn = "arn:aws:elasticloadbalancing:ap-southeast-1:007477962703:targetgroup/x/1", arn_suffix = "targetgroup/x/1" } }
  mock_resource "aws_cloudfront_function" { defaults = { arn = "arn:aws:cloudfront::007477962703:function/x" } }
  mock_resource "aws_cloudfront_distribution" { defaults = { arn = "arn:aws:cloudfront::007477962703:distribution/E1" } }
  mock_resource "aws_cloudwatch_log_group" { defaults = { arn = "arn:aws:logs:ap-southeast-1:007477962703:log-group:x" } }
  mock_resource "aws_iam_role" { defaults = { arn = "arn:aws:iam::007477962703:role/x" } }
  mock_resource "aws_iam_openid_connect_provider" { defaults = { arn = "arn:aws:iam::007477962703:oidc-provider/token.actions.githubusercontent.com" } }
  mock_resource "aws_sns_topic" { defaults = { arn = "arn:aws:sns:ap-southeast-1:007477962703:alarms" } }
  mock_resource "aws_kms_key" { defaults = { arn = "arn:aws:kms:ap-southeast-1:007477962703:key/1" } }
  mock_resource "aws_s3_bucket" { defaults = { arn = "arn:aws:s3:::b" } }
  mock_resource "aws_sqs_queue" { defaults = { arn = "arn:aws:sqs:ap-southeast-1:007477962703:q" } }
  mock_resource "aws_ecr_repository" { defaults = { arn = "arn:aws:ecr:ap-southeast-1:007477962703:repository/raas/api" } }
  mock_resource "aws_ecs_cluster" { defaults = { arn = "arn:aws:ecs:ap-southeast-1:007477962703:cluster/raas-prod" } }
  mock_resource "aws_ecs_service" { defaults = { id = "arn:aws:ecs:ap-southeast-1:007477962703:service/raas-prod/api" } }
  mock_resource "aws_ecs_task_definition" { defaults = { arn = "arn:aws:ecs:ap-southeast-1:007477962703:task-definition/raas-prod-api:1" } }
  mock_resource "aws_bedrock_guardrail" { defaults = { guardrail_arn = "arn:aws:bedrock:ap-southeast-1:007477962703:guardrail/abc", guardrail_id = "abc" } }
  mock_resource "aws_backup_vault" { defaults = { arn = "arn:aws:backup:ap-southeast-1:007477962703:backup-vault:v" } }
  mock_resource "aws_backup_plan" { defaults = { arn = "arn:aws:backup:ap-southeast-1:007477962703:backup-plan:p" } }
  mock_resource "aws_wafv2_web_acl" { defaults = { arn = "arn:aws:wafv2:us-east-1:007477962703:global/webacl/x/1" } }
}
mock_provider "aws" {
  alias = "us_east_1"
  mock_resource "aws_wafv2_web_acl" { defaults = { arn = "arn:aws:wafv2:us-east-1:007477962703:global/webacl/x/1" } }
}
mock_provider "random" {}

run "first_apply" {
  command = apply
  assert {
    condition     = aws_ecs_service.api.desired_count == 0
    error_message = "no image means 0 tasks"
  }
}

run "with_image_and_liftproof" {
  command = apply
  variables {
    api_image_tag                 = "abc123"
    liftproof_security_group_id   = "sg-123"
    liftproof_instance_role_name  = "liftproof-raas-instance"
    bedrock_inference_profile_ids = ["apac.amazon.nova-lite-v1:0"]
  }
  assert {
    condition     = aws_appautoscaling_target.api[0].min_capacity == 2
    error_message = "autoscaling keeps at least 2 API tasks"
  }
}
