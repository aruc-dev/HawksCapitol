variable "aws_region" {
  description = "AWS region used for all HawksCapitol paper infrastructure."
  type        = string
  default     = "us-east-1"
}

variable "project_name" {
  description = "Name prefix for AWS resources."
  type        = string
  default     = "hawkscapitol"
}

variable "environment" {
  description = "Deployment environment. Keep paper unless live is explicitly approved."
  type        = string
  default     = "paper"

  validation {
    condition     = var.environment == "paper"
    error_message = "This Terraform deployment is paper-only. Live requires a separate approved module/change."
  }
}

variable "repository_url" {
  description = "Git repository cloned by EC2 user data."
  type        = string
  default     = "https://github.com/aruc-dev/HawksCapitol.git"
}

variable "repository_ref" {
  description = "Git branch or tag checked out by EC2 user data."
  type        = string
  default     = "main"

  validation {
    condition     = var.repository_ref == "main"
    error_message = "Paper deployment defaults to origin/main. Use a reviewed change before deploying another ref."
  }
}

variable "instance_type" {
  description = "EC2 instance type for the paper node."
  type        = string
  default     = "t3.micro"
}

variable "root_volume_size_gb" {
  description = "Root EBS volume size in GiB."
  type        = number
  default     = 30
}

variable "vpc_cidr" {
  description = "CIDR block for the dedicated HawksCapitol VPC."
  type        = string
  default     = "10.72.0.0/16"
}

variable "public_subnet_cidr" {
  description = "CIDR block for the public subnet hosting the paper EC2 instance."
  type        = string
  default     = "10.72.1.0/24"
}

variable "allowed_ssh_cidr_blocks" {
  description = "Optional CIDR blocks allowed to SSH to EC2. Leave empty and use SSM Session Manager by default."
  type        = list(string)
  default     = []
}

variable "dashboard_ingress_cidr_blocks" {
  description = "Optional CIDR blocks allowed to reach the read-only dashboard port. Leave empty unless explicitly needed."
  type        = list(string)
  default     = []
}

variable "ssh_key_name" {
  description = "Optional existing EC2 key pair name. SSM access works without this."
  type        = string
  default     = ""
}

variable "secret_name" {
  description = "AWS Secrets Manager secret name read by scripts/fetch_secrets.sh."
  type        = string
  default     = "hawkscapitol/keys"
}

variable "existing_secret_arn" {
  description = "Use an existing secret ARN instead of creating metadata for var.secret_name."
  type        = string
  default     = ""
}

variable "enable_systemd_timers" {
  description = "Enable HawksCapitol timers during bootstrap. Set true only after paper secret values exist."
  type        = bool
  default     = false
}

variable "extra_tags" {
  description = "Additional tags merged into all resources."
  type        = map(string)
  default     = {}
}
