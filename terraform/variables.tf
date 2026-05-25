variable "aws_region" {
  type    = string
  default = "us-east-1"
}

variable "app_name" {
  type    = string
  default = "moon"
}

variable "task_cpu" {
  type    = number
  default = 512
}

variable "task_memory" {
  type    = number
  default = 1024
}

variable "desired_count" {
  type    = number
  default = 1
}

variable "image_tag" {
  type    = string
  default = "4e765b724a4825b06ec9f232d716e8ec1966faf5"
}

variable "log_retention_days" {
  type    = number
  default = 30
}

variable "cloudflare_api_token" {
  type        = string
  sensitive   = true
  description = "Cloudflare API token. Needs Zone:DNS:Edit, Tunnel:Edit, Access:Edit permissions on groot.work"
}

variable "cloudflare_account_id" {
  type        = string
  description = "Cloudflare account ID — find it in the dashboard URL: dash.cloudflare.com/<account_id>"
}

variable "owner_email" {
  type        = string
  default     = "chiraag.aval@gmail.com"
  description = "Email address allowed through Cloudflare Access"
}

variable "moon_mock_tools" {
  type    = bool
  default = false
}

variable "moon_coordinator_model" {
  type    = string
  default = "claude-haiku-4-5-20251001"
}

variable "moon_agent_model" {
  type    = string
  default = "claude-sonnet-4-6"
}

variable "github_repo" {
  type        = string
  description = "GitHub repo allowed to assume the CI role. Format: org/repo (e.g. chiraag-aval/moon)"
}
