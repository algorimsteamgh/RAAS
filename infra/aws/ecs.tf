# ECS Fargate: API service behind the ALB (min 2 tasks across 2 AZs), SQS
# worker service, and a one-off migration/data-load task definition.
# With api_image_tag empty (no image pushed yet) both services run 0 tasks.

resource "aws_ecs_cluster" "main" {
  name = local.name
  setting {
    name  = "containerInsights"
    value = "enabled"
  }
}

resource "aws_ecs_cluster_capacity_providers" "main" {
  cluster_name       = aws_ecs_cluster.main.name
  capacity_providers = ["FARGATE", "FARGATE_SPOT"]
  default_capacity_provider_strategy {
    capacity_provider = "FARGATE"
    weight            = 1
  }
}

resource "aws_cloudwatch_log_group" "app" {
  for_each          = toset(["api", "worker", "migrate"])
  name              = "/raas/${var.environment}/${each.key}"
  retention_in_days = var.log_retention_days
  kms_key_id        = aws_kms_key.logs.arn
}

locals {
  db_secret_arn = aws_db_instance.main.master_user_secret[0].secret_arn

  app_env = merge({
    APP_ENV              = var.environment
    AWS_REGION           = var.region
    MODEL_BACKEND        = "bedrock"
    BEDROCK_MODEL_ID     = try(var.bedrock_foundation_model_ids[0], "")
    DATABASE_HOST        = aws_db_instance.main.address
    DATABASE_PORT        = tostring(aws_db_instance.main.port)
    DATABASE_NAME        = var.db_name
    DATABASE_SSLMODE     = "require"
    CV_BUCKET            = aws_s3_bucket.cvs.bucket
    CV_BUCKET_KMS_KEY_ID = aws_kms_key.data.arn
    BATCH_QUEUE_URL      = aws_sqs_queue.batch.url
    SEED_DEMO_DATA       = "false"
  }, var.app_environment)

  # Until the app reads an IAM-auth/rotating credential, it gets the RDS-managed
  # master secret. Rotation changes the password: tasks pick it up on restart.
  app_secrets = [
    { name = "DATABASE_USER", valueFrom = "${local.db_secret_arn}:username::" },
    { name = "DATABASE_PASSWORD", valueFrom = "${local.db_secret_arn}:password::" },
  ]

  container_base = {
    image                  = local.api_image
    essential              = true
    environment            = [for k, v in local.app_env : { name = k, value = v }]
    secrets                = local.app_secrets
    readonlyRootFilesystem = false
    linuxParameters        = { initProcessEnabled = true }
  }
}

resource "aws_ecs_task_definition" "api" {
  family                   = "${local.name}-api"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = var.api_cpu
  memory                   = var.api_memory
  execution_role_arn       = aws_iam_role.ecs_execution.arn
  task_role_arn            = aws_iam_role.api_task.arn
  runtime_platform {
    operating_system_family = "LINUX"
    cpu_architecture        = var.cpu_architecture
  }
  container_definitions = jsonencode([merge(local.container_base, {
    name         = "api"
    portMappings = [{ containerPort = local.api_port, protocol = "tcp" }]
    healthCheck = {
      command     = ["CMD-SHELL", "curl -fs http://localhost:${local.api_port}/healthz || exit 1"]
      interval    = 30
      timeout     = 5
      retries     = 3
      startPeriod = 60
    }
    logConfiguration = {
      logDriver = "awslogs"
      options = {
        awslogs-group         = aws_cloudwatch_log_group.app["api"].name
        awslogs-region        = var.region
        awslogs-stream-prefix = "api"
      }
    }
  })])
}

resource "aws_ecs_task_definition" "worker" {
  family                   = "${local.name}-worker"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = var.api_cpu
  memory                   = var.api_memory
  execution_role_arn       = aws_iam_role.ecs_execution.arn
  task_role_arn            = aws_iam_role.worker_task.arn
  runtime_platform {
    operating_system_family = "LINUX"
    cpu_architecture        = var.cpu_architecture
  }
  container_definitions = jsonencode([merge(local.container_base, {
    name    = "worker"
    command = var.worker_command
    logConfiguration = {
      logDriver = "awslogs"
      options = {
        awslogs-group         = aws_cloudwatch_log_group.app["worker"].name
        awslogs-region        = var.region
        awslogs-stream-prefix = "worker"
      }
    }
  })])
}

# One-off task: schema migrations and the SQLite-to-RDS load. Run with
# aws ecs run-task (see README). Uses the worker role (S3 + DB secret).
resource "aws_ecs_task_definition" "migrate" {
  family                   = "${local.name}-migrate"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = 1024
  memory                   = 4096
  execution_role_arn       = aws_iam_role.ecs_execution.arn
  task_role_arn            = aws_iam_role.worker_task.arn
  ephemeral_storage {
    size_in_gib = 50
  }
  runtime_platform {
    operating_system_family = "LINUX"
    cpu_architecture        = var.cpu_architecture
  }
  container_definitions = jsonencode([merge(local.container_base, {
    name    = "migrate"
    command = var.migrate_command
    logConfiguration = {
      logDriver = "awslogs"
      options = {
        awslogs-group         = aws_cloudwatch_log_group.app["migrate"].name
        awslogs-region        = var.region
        awslogs-stream-prefix = "migrate"
      }
    }
  })])
}

resource "aws_ecs_service" "api" {
  name                   = "api"
  cluster                = aws_ecs_cluster.main.id
  task_definition        = aws_ecs_task_definition.api.arn
  desired_count          = local.has_image ? var.api_min_tasks : 0
  launch_type            = "FARGATE"
  enable_execute_command = true
  propagate_tags         = "SERVICE"

  health_check_grace_period_seconds = 90

  network_configuration {
    subnets          = aws_subnet.app[*].id
    security_groups  = [aws_security_group.app.id]
    assign_public_ip = false
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.api.arn
    container_name   = "api"
    container_port   = local.api_port
  }

  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }

  deployment_minimum_healthy_percent = 100
  deployment_maximum_percent         = 200

  # Autoscaling owns the count once an image exists: registering the scalable
  # target with min_capacity 2 raises the service from 0 to 2 tasks.
  lifecycle {
    ignore_changes = [desired_count]
  }

  depends_on = [aws_lb_listener.main]
}

resource "aws_ecs_service" "worker" {
  name                   = "worker"
  cluster                = aws_ecs_cluster.main.id
  task_definition        = aws_ecs_task_definition.worker.arn
  desired_count          = local.has_image ? var.worker_desired_count : 0
  launch_type            = "FARGATE"
  enable_execute_command = true
  propagate_tags         = "SERVICE"

  network_configuration {
    subnets          = aws_subnet.app[*].id
    security_groups  = [aws_security_group.app.id]
    assign_public_ip = false
  }

  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }
}

# API autoscaling: CPU and ALB requests per target.
resource "aws_appautoscaling_target" "api" {
  count              = local.has_image ? 1 : 0
  service_namespace  = "ecs"
  resource_id        = "service/${aws_ecs_cluster.main.name}/${aws_ecs_service.api.name}"
  scalable_dimension = "ecs:service:DesiredCount"
  min_capacity       = var.api_min_tasks
  max_capacity       = var.api_max_tasks
}

resource "aws_appautoscaling_policy" "api_cpu" {
  count              = local.has_image ? 1 : 0
  name               = "cpu-60"
  policy_type        = "TargetTrackingScaling"
  service_namespace  = aws_appautoscaling_target.api[0].service_namespace
  resource_id        = aws_appautoscaling_target.api[0].resource_id
  scalable_dimension = aws_appautoscaling_target.api[0].scalable_dimension
  target_tracking_scaling_policy_configuration {
    target_value = 60
    predefined_metric_specification {
      predefined_metric_type = "ECSServiceAverageCPUUtilization"
    }
  }
}

resource "aws_appautoscaling_policy" "api_requests" {
  count              = local.has_image ? 1 : 0
  name               = "requests-per-target"
  policy_type        = "TargetTrackingScaling"
  service_namespace  = aws_appautoscaling_target.api[0].service_namespace
  resource_id        = aws_appautoscaling_target.api[0].resource_id
  scalable_dimension = aws_appautoscaling_target.api[0].scalable_dimension
  target_tracking_scaling_policy_configuration {
    target_value = 500
    predefined_metric_specification {
      predefined_metric_type = "ALBRequestCountPerTarget"
      resource_label         = "${aws_lb.main.arn_suffix}/${aws_lb_target_group.api.arn_suffix}"
    }
  }
}
