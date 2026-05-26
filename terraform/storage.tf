resource "aws_dynamodb_table" "moon_cases" {
  name         = "moon-cases"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "id"

  attribute {
    name = "id"
    type = "S"
  }

  tags = local.tags

  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_cloudwatch_log_group" "moon" {
  name              = "/ecs/${var.app_name}"
  retention_in_days = var.log_retention_days
  tags              = local.tags
}

data "aws_secretsmanager_secret" "github_token" {
  name = "moon/github-token"
}
