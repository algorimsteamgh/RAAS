# Roles for the ECS tasks. Execution role: pull image, write logs, read the DB
# secret at start. Task roles: what the code itself may call.

data "aws_iam_policy_document" "ecs_tasks_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"]
    }
    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [data.aws_caller_identity.current.account_id]
    }
  }
}

resource "aws_iam_role" "ecs_execution" {
  name               = "${local.name}-ecs-execution"
  assume_role_policy = data.aws_iam_policy_document.ecs_tasks_assume.json
}

resource "aws_iam_role_policy_attachment" "ecs_execution" {
  role       = aws_iam_role.ecs_execution.name
  policy_arn = "arn:${data.aws_partition.current.partition}:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

resource "aws_iam_role_policy" "ecs_execution_secrets" {
  name = "read-db-secret"
  role = aws_iam_role.ecs_execution.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["secretsmanager:GetSecretValue"]
        Resource = [aws_db_instance.main.master_user_secret[0].secret_arn]
      },
      {
        Effect   = "Allow"
        Action   = ["kms:Decrypt"]
        Resource = [aws_kms_key.data.arn]
      },
    ]
  })
}

# ---------------------------------------------------------------- Bedrock

locals {
  bedrock_model_arns = [
    for id in var.bedrock_foundation_model_ids :
    "arn:${data.aws_partition.current.partition}:bedrock:${var.region}::foundation-model/${id}"
  ]
  bedrock_profile_arns = [
    for id in var.bedrock_inference_profile_ids :
    "arn:${data.aws_partition.current.partition}:bedrock:${var.region}:${data.aws_caller_identity.current.account_id}:inference-profile/${id}"
  ]
  # A cross-region profile routes to the base model in other regions of the geography.
  bedrock_profile_model_arns = [
    for id in var.bedrock_inference_profile_ids :
    "arn:${data.aws_partition.current.partition}:bedrock:*::foundation-model/${join(".", slice(split(".", id), 1, length(split(".", id))))}"
  ]
}

data "aws_iam_policy_document" "bedrock_invoke" {
  statement {
    sid = "InvokeApprovedModels"
    actions = [
      "bedrock:InvokeModel",
      "bedrock:InvokeModelWithResponseStream", # Converse / ConverseStream use these
    ]
    resources = concat(local.bedrock_model_arns, local.bedrock_profile_arns, local.bedrock_profile_model_arns)
  }

  dynamic "statement" {
    for_each = length(var.bedrock_inference_profile_ids) > 0 ? [] : [1]
    content {
      sid       = "DenyCrossRegionInference"
      effect    = "Deny"
      actions   = ["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"]
      resources = ["arn:${data.aws_partition.current.partition}:bedrock:*:*:inference-profile/*"]
    }
  }

  statement {
    sid       = "ApplyGuardrails"
    actions   = ["bedrock:ApplyGuardrail"]
    resources = ["arn:${data.aws_partition.current.partition}:bedrock:${var.region}:${data.aws_caller_identity.current.account_id}:guardrail/*"]
  }
}

# ---------------------------------------------------------------- task roles

resource "aws_iam_role" "api_task" {
  name               = "${local.name}-api-task"
  assume_role_policy = data.aws_iam_policy_document.ecs_tasks_assume.json
}

resource "aws_iam_role" "worker_task" {
  name               = "${local.name}-worker-task"
  assume_role_policy = data.aws_iam_policy_document.ecs_tasks_assume.json
}

data "aws_iam_policy_document" "app_common" {
  statement {
    sid       = "CvObjects"
    actions   = ["s3:GetObject", "s3:GetObjectVersion", "s3:PutObject", "s3:GetObjectAttributes"]
    resources = ["${aws_s3_bucket.cvs.arn}/*"]
  }
  statement {
    sid       = "CvList"
    actions   = ["s3:ListBucket"]
    resources = [aws_s3_bucket.cvs.arn]
  }
  statement {
    sid       = "DataKey"
    actions   = ["kms:Decrypt", "kms:GenerateDataKey"]
    resources = [aws_kms_key.data.arn]
  }
  statement {
    sid       = "DbSecret"
    actions   = ["secretsmanager:GetSecretValue"]
    resources = [aws_db_instance.main.master_user_secret[0].secret_arn]
  }
}

resource "aws_iam_role_policy" "api_common" {
  name   = "app-common"
  role   = aws_iam_role.api_task.id
  policy = data.aws_iam_policy_document.app_common.json
}

resource "aws_iam_role_policy" "api_bedrock" {
  name   = "bedrock"
  role   = aws_iam_role.api_task.id
  policy = data.aws_iam_policy_document.bedrock_invoke.json
}

resource "aws_iam_role_policy" "api_sqs" {
  name = "sqs-send"
  role = aws_iam_role.api_task.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["sqs:SendMessage", "sqs:GetQueueAttributes", "sqs:GetQueueUrl"]
      Resource = [aws_sqs_queue.batch.arn]
    }]
  })
}

resource "aws_iam_role_policy" "worker_common" {
  name   = "app-common"
  role   = aws_iam_role.worker_task.id
  policy = data.aws_iam_policy_document.app_common.json
}

resource "aws_iam_role_policy" "worker_bedrock" {
  name   = "bedrock"
  role   = aws_iam_role.worker_task.id
  policy = data.aws_iam_policy_document.bedrock_invoke.json
}

resource "aws_iam_role_policy" "worker_sqs" {
  name = "sqs-consume"
  role = aws_iam_role.worker_task.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = [
        "sqs:ReceiveMessage", "sqs:DeleteMessage", "sqs:ChangeMessageVisibility",
        "sqs:GetQueueAttributes", "sqs:GetQueueUrl",
      ]
      Resource = [aws_sqs_queue.batch.arn]
    }]
  })
}

# ECS Exec (break-glass shell into a task via Session Manager) for both roles.
resource "aws_iam_role_policy" "ecs_exec" {
  for_each = { api = aws_iam_role.api_task.id, worker = aws_iam_role.worker_task.id }
  name     = "ecs-exec"
  role     = each.value
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = [
        "ssmmessages:CreateControlChannel", "ssmmessages:CreateDataChannel",
        "ssmmessages:OpenControlChannel", "ssmmessages:OpenDataChannel",
      ]
      Resource = "*"
    }]
  })
}

# ---------------------------------------------------------------- Liftproof read access

resource "aws_iam_role_policy" "liftproof_cv_read" {
  count = var.liftproof_instance_role_name != "" ? 1 : 0
  name  = "read-raas-cvs"
  role  = var.liftproof_instance_role_name
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["s3:GetObject", "s3:GetObjectVersion"]
        Resource = "${aws_s3_bucket.cvs.arn}/*"
      },
      {
        Effect   = "Allow"
        Action   = "s3:ListBucket"
        Resource = aws_s3_bucket.cvs.arn
      },
      {
        Effect   = "Allow"
        Action   = "kms:Decrypt"
        Resource = aws_kms_key.data.arn
      },
    ]
  })
}
