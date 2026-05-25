resource "aws_ecr_repository" "moon" {
  name                 = var.app_name
  image_tag_mutability = "IMMUTABLE"
  tags                 = local.tags

  image_scanning_configuration {
    scan_on_push = true
  }
}

resource "aws_ecr_lifecycle_policy" "moon" {
  repository = aws_ecr_repository.moon.name

  policy = jsonencode({
    rules = [{
      rulePriority = 1
      description  = "Keep last 10 images"
      selection = {
        tagStatus   = "any"
        countType   = "imageCountMoreThan"
        countNumber = 10
      }
      action = { type = "expire" }
    }]
  })
}

resource "aws_ecs_cluster" "moon" {
  name = var.app_name
  tags = local.tags
}

resource "aws_ecs_task_definition" "moon" {
  family                   = var.app_name
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = var.task_cpu
  memory                   = var.task_memory
  execution_role_arn       = aws_iam_role.moon_execution.arn
  task_role_arn            = aws_iam_role.moon_task.arn
  tags                     = local.tags

  container_definitions = jsonencode([{
    name      = var.app_name
    image     = "${aws_ecr_repository.moon.repository_url}:${var.image_tag}"
    essential = true

    portMappings = [{
      containerPort = 8000
      protocol      = "tcp"
    }]

    environment = [
      { name = "MOON_DYNAMO_TABLE",      value = aws_dynamodb_table.moon_cases.name },
      { name = "MOON_DYNAMO_REGION",     value = var.aws_region },
      { name = "MOON_MOCK_TOOLS",        value = tostring(var.moon_mock_tools) },
      { name = "MOON_COORDINATOR_MODEL", value = var.moon_coordinator_model },
      { name = "MOON_AGENT_MODEL",       value = var.moon_agent_model },
    ]

    secrets = [
      { name = "ANTHROPIC_API_KEY", valueFrom = "${data.aws_secretsmanager_secret.anthropic_api_key.arn}:anthropic-api-key::" },
      { name = "GITHUB_TOKEN",      valueFrom = "${data.aws_secretsmanager_secret.github_token.arn}:moon/github-token::" },
    ]

    dependsOn = [{
      containerName = "cloudflared"
      condition     = "START"
    }]

    healthCheck = {
      command     = ["CMD-SHELL", "python3 -c \"import urllib.request; urllib.request.urlopen('http://localhost:8000/')\" 2>/dev/null || exit 1"]
      interval    = 30
      timeout     = 5
      retries     = 3
      startPeriod = 60
    }

    logConfiguration = {
      logDriver = "awslogs"
      options = {
        "awslogs-group"         = aws_cloudwatch_log_group.moon.name
        "awslogs-region"        = var.aws_region
        "awslogs-stream-prefix" = "ecs"
      }
    }
  },
  {
    name      = "cloudflared"
    image     = "cloudflare/cloudflared:latest"
    essential = false
    command   = ["tunnel", "--no-autoupdate", "run"]

    secrets = [
      { name = "TUNNEL_TOKEN", valueFrom = "${aws_secretsmanager_secret.tunnel_token.arn}:tunnel-token::" }
    ]

    logConfiguration = {
      logDriver = "awslogs"
      options = {
        "awslogs-group"         = aws_cloudwatch_log_group.moon.name
        "awslogs-region"        = var.aws_region
        "awslogs-stream-prefix" = "cloudflared"
      }
    }
  }])
}

resource "aws_ecs_service" "moon" {
  name            = var.app_name
  cluster         = aws_ecs_cluster.moon.id
  task_definition = aws_ecs_task_definition.moon.arn
  desired_count   = var.desired_count
  launch_type     = "FARGATE"
  tags            = local.tags

  network_configuration {
    subnets          = data.aws_subnets.default.ids
    security_groups  = [aws_security_group.moon.id]
    assign_public_ip = true
  }

  lifecycle {
    ignore_changes = [task_definition]
  }
}
