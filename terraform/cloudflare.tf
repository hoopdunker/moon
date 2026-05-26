provider "cloudflare" {
  api_token = var.cloudflare_api_token
}

data "cloudflare_zone" "groot_work" {
  name = "groot.work"
}

# ── Tunnel ────────────────────────────────────────────────────────────────────

resource "random_id" "tunnel_secret" {
  byte_length = 32
}

resource "cloudflare_zero_trust_tunnel_cloudflared" "moon" {
  account_id = var.cloudflare_account_id
  name       = "moon"
  secret     = random_id.tunnel_secret.b64_std
}

resource "cloudflare_zero_trust_tunnel_cloudflared_config" "moon" {
  account_id = var.cloudflare_account_id
  tunnel_id  = cloudflare_zero_trust_tunnel_cloudflared.moon.id

  config {
    ingress_rule {
      hostname = "moon.groot.work"
      service  = "http://localhost:8000"
    }
    ingress_rule {
      hostname = "intel.groot.work"
      service  = "http://localhost:8000"
    }
    # Catch-all — required by Cloudflare
    ingress_rule {
      service = "http_status:404"
    }
  }
}

# Store tunnel token in Secrets Manager so ECS can inject it at runtime
resource "aws_secretsmanager_secret" "tunnel_token" {
  name        = "moon/cloudflare-tunnel-token"
  description = "Cloudflare tunnel token for the cloudflared sidecar"
  tags        = local.tags
}

resource "aws_secretsmanager_secret_version" "tunnel_token" {
  secret_id     = aws_secretsmanager_secret.tunnel_token.id
  secret_string = jsonencode({ "tunnel-token" = cloudflare_zero_trust_tunnel_cloudflared.moon.tunnel_token })
}

# ── DNS ───────────────────────────────────────────────────────────────────────

resource "cloudflare_record" "moon" {
  zone_id = data.cloudflare_zone.groot_work.id
  name    = "moon"
  content = "${cloudflare_zero_trust_tunnel_cloudflared.moon.id}.cfargotunnel.com"
  type    = "CNAME"
  proxied = true
}

resource "cloudflare_record" "intel" {
  zone_id = data.cloudflare_zone.groot_work.id
  name    = "intel"
  content = "${cloudflare_zero_trust_tunnel_cloudflared.moon.id}.cfargotunnel.com"
  type    = "CNAME"
  proxied = true
}

# ── Cloudflare Access ─────────────────────────────────────────────────────────

resource "cloudflare_zero_trust_access_application" "moon" {
  zone_id          = data.cloudflare_zone.groot_work.id
  name             = "Moon"
  domain           = "moon.groot.work"
  type             = "self_hosted"
  session_duration = "24h"
}

resource "cloudflare_zero_trust_access_policy" "moon_allow" {
  application_id = cloudflare_zero_trust_access_application.moon.id
  zone_id        = data.cloudflare_zone.groot_work.id
  name           = "Allow owner"
  precedence     = 1
  decision       = "allow"

  include {
    email = [var.owner_email]
  }
}

resource "cloudflare_zero_trust_access_application" "intel" {
  zone_id          = data.cloudflare_zone.groot_work.id
  name             = "Moon Intel"
  domain           = "intel.groot.work"
  type             = "self_hosted"
  session_duration = "24h"
}

resource "cloudflare_zero_trust_access_policy" "intel_allow" {
  application_id = cloudflare_zero_trust_access_application.intel.id
  zone_id        = data.cloudflare_zone.groot_work.id
  name           = "Allow owner"
  precedence     = 1
  decision       = "allow"

  include {
    email = [var.owner_email]
  }
}
