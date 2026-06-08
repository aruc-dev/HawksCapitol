locals {
  name_prefix = "${var.project_name}-${var.environment}"

  tags = merge(
    {
      Project     = "HawksCapitol"
      Environment = var.environment
      ManagedBy   = "terraform"
      Mode        = "paper"
    },
    var.extra_tags
  )

  secret_arn = var.existing_secret_arn != "" ? var.existing_secret_arn : aws_secretsmanager_secret.paper_keys[0].arn

  systemd_timers = [
    "hawkscapitol-ingest.timer",
    "hawkscapitol-score.timer",
    "hawkscapitol-scan.timer",
    "hawkscapitol-risk-check.timer",
    "hawkscapitol-daily-report.timer",
    "hawkscapitol-weekly-report.timer",
    "hawkscapitol-health-check.timer",
  ]
}
