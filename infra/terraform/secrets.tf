resource "aws_secretsmanager_secret" "paper_keys" {
  count = var.existing_secret_arn == "" ? 1 : 0

  name        = var.secret_name
  description = "HawksCapitol paper credentials. Secret values must be written outside Terraform."

  recovery_window_in_days = 7

  tags = {
    Name = var.secret_name
  }
}
