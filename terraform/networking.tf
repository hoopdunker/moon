data "aws_vpc" "default" {
  default = true
}

data "aws_subnets" "default" {
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.default.id]
  }
}

resource "aws_security_group" "moon" {
  name        = "${var.app_name}-sg"
  description = "Moon ECS service"
  vpc_id      = data.aws_vpc.default.id

  # No inbound rules — all traffic arrives via Cloudflare Tunnel (outbound only)
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = local.tags
}
