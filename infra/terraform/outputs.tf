output "instance_id" {
  description = "HawksCapitol paper EC2 instance ID."
  value       = aws_instance.paper_node.id
}

output "instance_public_dns" {
  description = "Public DNS for optional SSH access. Prefer SSM Session Manager when possible."
  value       = aws_instance.paper_node.public_dns
}

output "instance_public_ip" {
  description = "Public IP for optional SSH access."
  value       = aws_instance.paper_node.public_ip
}

output "secret_arn" {
  description = "Secrets Manager ARN read by the EC2 instance profile."
  value       = local.secret_arn
}

output "ssm_connect_command" {
  description = "Command to start an SSM Session Manager shell."
  value       = "aws ssm start-session --target ${aws_instance.paper_node.id} --region ${var.aws_region}"
}

output "systemd_timer_units" {
  description = "HawksCapitol timers installed by user data."
  value       = local.systemd_timers
}
