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
  default = "latest"
}

variable "log_retention_days" {
  type    = number
  default = 30
}

variable "allowed_cidr" {
  type        = string
  description = "CIDR allowed to reach port 8000. Restrict to your IP: $(curl -s ifconfig.me)/32"
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
