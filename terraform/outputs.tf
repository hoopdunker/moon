output "ecr_repository_url" {
  value       = aws_ecr_repository.moon.repository_url
  description = "Push images here: docker push <url>:<tag>"
}

output "ecs_cluster_name" {
  value = aws_ecs_cluster.moon.name
}

output "ecs_service_name" {
  value = aws_ecs_service.moon.name
}

output "dynamodb_table_name" {
  value = aws_dynamodb_table.moon_cases.name
}

output "dynamodb_table_arn" {
  value = aws_dynamodb_table.moon_cases.arn
}

output "log_group_name" {
  value       = aws_cloudwatch_log_group.moon.name
  description = "Tail logs: aws logs tail /ecs/moon --follow"
}

output "moon_url" {
  value       = "https://moon.groot.work"
  description = "Moon dashboard — protected by Cloudflare Access"
}

output "tunnel_id" {
  value       = cloudflare_zero_trust_tunnel_cloudflared.moon.id
  description = "Cloudflare Tunnel ID"
}
