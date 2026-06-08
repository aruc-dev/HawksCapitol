from __future__ import annotations

import unittest
from pathlib import Path

from core.config_loader import load_structured_file


REPO_ROOT = Path(__file__).resolve().parents[1]


class DocumentationContractTests(unittest.TestCase):
    def test_agent_workflow_requires_documentation_check(self) -> None:
        agents = (REPO_ROOT / "AGENTS.md").read_text(encoding="utf-8")
        skill = (REPO_ROOT / "SKILL.md").read_text(encoding="utf-8")
        plan = (REPO_ROOT / "plan.md").read_text(encoding="utf-8")
        testing = (REPO_ROOT / "TESTING.md").read_text(encoding="utf-8")
        readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")

        self.assertIn("Documentation Check Required For Every Change", agents)
        for text in (agents, skill, plan, testing, readme):
            self.assertIn("documentation check", text.lower())

    def test_public_docs_list_current_validation_commands(self) -> None:
        for filename in ("README.md", "TESTING.md"):
            text = (REPO_ROOT / filename).read_text(encoding="utf-8")
            with self.subTest(filename=filename):
                self.assertIn("python3 scheduler/run_weekly_report.py --dry-run", text)
                self.assertIn("python3 scheduler/run_live_promotion_check.py --dry-run", text)
                self.assertIn("scripts/validate_terraform.sh", text)
                self.assertIn("scripts/validate_paper_deploy.sh", text)

    def test_architecture_reflects_implemented_paper_ready_state(self) -> None:
        text = (REPO_ROOT / "architecture.md").read_text(encoding="utf-8")

        self.assertNotIn("pre-implementation", text)
        self.assertIn("Implemented locally", text)
        self.assertIn("run_live_promotion_check.py", text)
        self.assertIn("validate_paper_deploy.sh", text)
        self.assertIn("Terraform", text)
        self.assertIn("Documentation discipline", text)

    def test_deployment_docs_are_terraform_first(self) -> None:
        agents = (REPO_ROOT / "AGENTS.md").read_text(encoding="utf-8")
        cloud_setup = (REPO_ROOT / "cloud-setup" / "aws-setup-systemd.md").read_text(encoding="utf-8")
        terraform_readme = (REPO_ROOT / "infra" / "terraform" / "README.md").read_text(encoding="utf-8")

        for text in (agents, cloud_setup, terraform_readme):
            self.assertIn("Terraform", text)
        self.assertIn("Terraform First", cloud_setup)
        self.assertIn("GitHub Actions", cloud_setup)
        self.assertIn("Secret values must be written outside Terraform", terraform_readme)

    def test_source_docs_cover_registry_entries(self) -> None:
        source_docs = (REPO_ROOT / "docs" / "sources.md").read_text(encoding="utf-8")
        registry = load_structured_file(REPO_ROOT / "config" / "source_registry.yaml")

        for entry in registry["sources"]:
            self.assertIn(f"`{entry['name']}`", source_docs)


if __name__ == "__main__":
    unittest.main()
