resource "aws_iam_role" "moon_execution" {
  name = "moon-execution-role"
  tags = local.tags

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "ecs-tasks.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy_attachment" "moon_execution" {
  role       = aws_iam_role.moon_execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

resource "aws_iam_role_policy" "moon_execution_secrets" {
  name = "moon-execution-secrets"
  role = aws_iam_role.moon_execution.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = ["secretsmanager:GetSecretValue"]
      Resource = [
        data.aws_secretsmanager_secret.anthropic_api_key.arn,
        data.aws_secretsmanager_secret.github_token.arn,
        aws_secretsmanager_secret.tunnel_token.arn,
      ]
    }]
  })
}

resource "aws_iam_role" "moon_task" {
  name = "moon-task-role"
  tags = local.tags

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "ecs-tasks.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy" "moon_task_dynamodb" {
  name = "moon-task-dynamodb"
  role = aws_iam_role.moon_task.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = [
        "dynamodb:GetItem",
        "dynamodb:PutItem",
        "dynamodb:Scan",
        "dynamodb:DescribeTable"
      ]
      Resource = aws_dynamodb_table.moon_cases.arn
    }]
  })
}

resource "aws_iam_role_policy" "moon_task_bedrock" {
  name = "moon-task-bedrock"
  role = aws_iam_role.moon_task.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["bedrock:InvokeModel"]
      Resource = "arn:aws:bedrock:*::foundation-model/anthropic.*"
    }]
  })
}
