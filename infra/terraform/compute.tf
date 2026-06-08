resource "aws_instance" "paper_node" {
  ami                         = data.aws_ssm_parameter.al2023_ami.value
  instance_type               = var.instance_type
  subnet_id                   = aws_subnet.public.id
  vpc_security_group_ids      = [aws_security_group.paper_node.id]
  iam_instance_profile        = aws_iam_instance_profile.paper_node.name
  associate_public_ip_address = true
  key_name                    = var.ssh_key_name != "" ? var.ssh_key_name : null
  user_data_replace_on_change = true

  user_data = templatefile("${path.module}/user_data.sh.tftpl", {
    repository_url        = var.repository_url
    repository_ref        = var.repository_ref
    secret_name           = var.secret_name
    enable_systemd_timers = var.enable_systemd_timers
    systemd_timers        = local.systemd_timers
  })

  root_block_device {
    volume_size           = var.root_volume_size_gb
    volume_type           = "gp3"
    encrypted             = true
    delete_on_termination = true
  }

  metadata_options {
    http_endpoint = "enabled"
    http_tokens   = "required"
  }

  tags = {
    Name = "${local.name_prefix}-paper-node"
  }
}
