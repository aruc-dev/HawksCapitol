from __future__ import annotations

import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
TERRAFORM_DIR = REPO_ROOT / "infra" / "terraform"


class TerraformDeploymentTests(unittest.TestCase):
    def _terraform_text(self) -> str:
        return "\n".join(path.read_text(encoding="utf-8") for path in TERRAFORM_DIR.glob("*.tf"))

    def test_terraform_root_module_contains_paper_aws_runtime(self) -> None:
        text = self._terraform_text()

        for expected in (
            'required_version = ">= 1.6.0"',
            'source  = "hashicorp/aws"',
            'resource "aws_vpc" "main"',
            'resource "aws_subnet" "public"',
            'resource "aws_security_group" "paper_node"',
            'resource "aws_iam_role" "paper_node"',
            'resource "aws_iam_instance_profile" "paper_node"',
            'resource "aws_instance" "paper_node"',
            'resource "aws_secretsmanager_secret" "paper_keys"',
            "AmazonSSMManagedInstanceCore",
            "secretsmanager:GetSecretValue",
            "http_tokens   = \"required\"",
            "user_data.sh.tftpl",
        ):
            self.assertIn(expected, text)

    def test_terraform_is_paper_only_and_keeps_secret_values_out_of_state(self) -> None:
        text = self._terraform_text()
        tfvars = (TERRAFORM_DIR / "terraform.tfvars.example").read_text(encoding="utf-8")
        user_data = (TERRAFORM_DIR / "user_data.sh.tftpl").read_text(encoding="utf-8")

        self.assertIn('var.environment == "paper"', text)
        self.assertIn('repository_ref == "main"', text)
        self.assertNotIn("aws_secretsmanager_secret_version", text)
        self.assertIn("Secret values must be written outside Terraform", text)
        self.assertNotIn("ALPACA_SECRET_KEY", tfvars)
        self.assertNotIn("ALPACA_API_KEY", tfvars)
        self.assertIn('cfg["mode"] != "paper"', user_data)
        self.assertIn('execution.allow_live=true', user_data)

    def test_user_data_bootstraps_systemd_and_safe_validation(self) -> None:
        text = (TERRAFORM_DIR / "user_data.sh.tftpl").read_text(encoding="utf-8")

        for expected in (
            "git clone",
            "git reset --hard",
            "pip install -r requirements.txt",
            "cp scheduler/systemd/hawkscapitol-*.service",
            "hawkscapitol-secrets.service.d",
            'Environment="HAWKSCAPITOL_SECRET_ID=$${secret_name}"',
            "systemctl daemon-reload",
            "HAWKSCAPITOL_DRY_RUN=1 scripts/fetch_secrets.sh",
            "python3 -m unittest discover -v",
            "python3 scheduler/run_health_check.py --dry-run",
            "python3 scheduler/run_live_promotion_check.py --dry-run",
            "enable_systemd_timers",
        ):
            self.assertIn(expected, text)

    def test_github_actions_workflow_uses_oidc_and_remote_backend(self) -> None:
        workflow = (REPO_ROOT / ".github" / "workflows" / "terraform-deploy.yml").read_text(encoding="utf-8")

        self.assertIn("workflow_dispatch", workflow)
        self.assertIn("id-token: write", workflow)
        self.assertIn("aws-actions/configure-aws-credentials@v4", workflow)
        self.assertIn("role-to-assume: ${{ vars.AWS_ROLE_TO_ASSUME }}", workflow)
        self.assertIn('backend "s3"', workflow)
        self.assertIn("terraform plan -out=tfplan", workflow)
        self.assertIn("terraform apply -auto-approve tfplan", workflow)
        self.assertNotIn("AWS_ACCESS_KEY_ID", workflow)
        self.assertNotIn("AWS_SECRET_ACCESS_KEY", workflow)

    def test_terraform_artifacts_and_state_are_gitignored(self) -> None:
        ignore = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8")

        for expected in (
            ".terraform/",
            "*.tfstate",
            "*.tfplan",
            "tfplan",
            "backend.tf",
            "infra/terraform/terraform.tfvars",
        ):
            self.assertIn(expected, ignore)

    def test_validate_terraform_script_is_safe_without_terraform_binary(self) -> None:
        text = (REPO_ROOT / "scripts" / "validate_terraform.sh").read_text(encoding="utf-8")

        self.assertIn("command -v terraform", text)
        self.assertIn("terraform not installed; skipping", text)
        self.assertIn("terraform -chdir=infra/terraform fmt -check", text)
        self.assertIn("terraform -chdir=infra/terraform validate", text)


if __name__ == "__main__":
    unittest.main()
