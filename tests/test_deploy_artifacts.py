from __future__ import annotations

import json
import os
import plistlib
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path

from scheduler import run_weekly_report


REPO_ROOT = Path(__file__).resolve().parents[1]
SYSTEMD_DIR = REPO_ROOT / "scheduler" / "systemd"
SCHEDULED_JOBS = {
    "ingest": "scheduler/run_ingest.py",
    "score": "scheduler/run_score.py",
    "scan": "scheduler/run_scan.py",
    "risk-check": "scheduler/run_risk_check.py",
    "daily-report": "scheduler/run_report.py",
    "weekly-report": "scheduler/run_weekly_report.py",
    "health-check": "scheduler/run_health_check.py",
}


class DeployArtifactTests(unittest.TestCase):
    def test_systemd_services_require_tmpfs_secrets_before_work(self) -> None:
        for name, script in SCHEDULED_JOBS.items():
            with self.subTest(name=name):
                text = (SYSTEMD_DIR / f"hawkscapitol-{name}.service").read_text(encoding="utf-8")
                after_line = next(line for line in text.splitlines() if line.startswith("After="))

                self.assertIn("Requires=hawkscapitol-secrets.service", text)
                self.assertIn("network-online.target", after_line)
                self.assertIn("hawkscapitol-secrets.service", after_line)
                self.assertIn("Environment=HAWKSCAPITOL_REQUIRE_SHM=1", text)
                self.assertIn("EnvironmentFile=/dev/shm/.hawkscapitol.env", text)
                self.assertIn(f"ExecStart=/home/ec2-user/HawksCapitol/.venv/bin/python {script}", text)

    def test_systemd_timers_have_matching_units(self) -> None:
        for name in [*SCHEDULED_JOBS, "secrets"]:
            with self.subTest(name=name):
                text = (SYSTEMD_DIR / f"hawkscapitol-{name}.timer").read_text(encoding="utf-8")

                self.assertIn(f"Unit=hawkscapitol-{name}.service", text)
                self.assertIn("WantedBy=timers.target", text)
                self.assertTrue("OnCalendar=" in text or "OnBootSec=" in text)

    def test_secrets_service_runs_before_scheduled_jobs(self) -> None:
        text = (SYSTEMD_DIR / "hawkscapitol-secrets.service").read_text(encoding="utf-8")
        before_line = next(line for line in text.splitlines() if line.startswith("Before="))

        self.assertIn("ExecStart=/home/ec2-user/HawksCapitol/scripts/fetch_secrets.sh", text)
        self.assertIn("HAWKSCAPITOL_SECRET_ID=hawkscapitol/keys", text)
        self.assertIn("HAWKSCAPITOL_ENV_FILE=/dev/shm/.hawkscapitol.env", text)
        for name in SCHEDULED_JOBS:
            self.assertIn(f"hawkscapitol-{name}.service", before_line)

    def test_fetch_secrets_dry_run_and_validation_are_redacted(self) -> None:
        env = os.environ.copy()
        env.update({"HAWKSCAPITOL_DRY_RUN": "1", "HAWKSCAPITOL_ENV_FILE": "/tmp/hc-test.env"})
        dry_run = subprocess.run(
            ["bash", "scripts/fetch_secrets.sh"],
            cwd=REPO_ROOT,
            env=env,
            capture_output=True,
            text=True,
            check=True,
        )
        self.assertIn("values redacted", dry_run.stdout)
        self.assertNotIn("ALPACA_SECRET_KEY=", dry_run.stdout)

        blocked_env = os.environ.copy()
        blocked_env.update(
            {
                "HAWKSCAPITOL_DRY_RUN": "1",
                "HAWKSCAPITOL_REQUIRE_SHM": "1",
                "HAWKSCAPITOL_ENV_FILE": "/tmp/hc-test.env",
            }
        )
        blocked = subprocess.run(
            ["bash", "scripts/fetch_secrets.sh"],
            cwd=REPO_ROOT,
            env=blocked_env,
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(blocked.returncode, 0)
        self.assertIn("refusing to write secrets outside /dev/shm", blocked.stderr)

        with tempfile.NamedTemporaryFile() as handle:
            Path(handle.name).chmod(stat.S_IRUSR | stat.S_IWUSR)
            validate_env = os.environ.copy()
            validate_env.update({"HAWKSCAPITOL_VALIDATE_ONLY": "1", "HAWKSCAPITOL_ENV_FILE": handle.name})
            validated = subprocess.run(
                ["bash", "scripts/fetch_secrets.sh"],
                cwd=REPO_ROOT,
                env=validate_env,
                capture_output=True,
                text=True,
                check=True,
            )
            self.assertIn("validation ok", validated.stdout)

        with tempfile.TemporaryDirectory() as tmp:
            aws_cli = Path(tmp) / "fake-aws"
            env_file = Path(tmp) / "hawks.env"
            aws_cli.write_text(
                "#!/usr/bin/env bash\nprintf '%s\\n' 'ALPACA_API_KEY=key with spaces' 'ALPACA_SECRET_KEY=value$(echo pwn)'\n",
                encoding="utf-8",
            )
            aws_cli.chmod(0o755)
            line_env = os.environ.copy()
            line_env.update({"AWS_CLI": str(aws_cli), "HAWKSCAPITOL_ENV_FILE": str(env_file)})
            subprocess.run(
                ["bash", "scripts/fetch_secrets.sh"],
                cwd=REPO_ROOT,
                env=line_env,
                capture_output=True,
                text=True,
                check=True,
            )
            rendered = env_file.read_text(encoding="utf-8")
            self.assertIn("ALPACA_API_KEY='key with spaces'", rendered)
            self.assertIn("ALPACA_SECRET_KEY='value$(echo pwn)'", rendered)
            sourced = subprocess.run(
                ["bash", "-c", f". {env_file}; printf '%s' \"$ALPACA_SECRET_KEY\""],
                capture_output=True,
                text=True,
                check=True,
            )
            self.assertEqual(sourced.stdout, "value$(echo pwn)")

    def test_cron_and_launchd_reference_all_scheduler_jobs(self) -> None:
        cron_text = (REPO_ROOT / "cron" / "hawkscapitol.crontab").read_text(encoding="utf-8")
        for script in SCHEDULED_JOBS.values():
            self.assertIn(script, cron_text)

        for name, script in SCHEDULED_JOBS.items():
            label_name = name.replace("_", "-")
            path = REPO_ROOT / "launchd" / f"com.hawkscapitol.{label_name}.plist"
            with self.subTest(path=path.name):
                with path.open("rb") as handle:
                    payload = plistlib.load(handle)
                command = " ".join(payload["ProgramArguments"])

                self.assertEqual(payload["Label"], f"com.hawkscapitol.{label_name}")
                self.assertEqual(payload["EnvironmentVariables"]["HAWKSCAPITOL_REQUIRE_SHM"], "0")
                self.assertIn(script, command)

    def test_weekly_report_runner_is_json_safe(self) -> None:
        payload = run_weekly_report.run(dry_run=True)

        self.assertEqual(payload["period"], "weekly")
        self.assertIn("member_performance", payload)
        self.assertIn("sector_performance", payload)
        json.dumps(payload)

    def test_paper_deploy_validator_covers_local_safety_gates(self) -> None:
        text = (REPO_ROOT / "scripts" / "validate_paper_deploy.sh").read_text(encoding="utf-8")

        self.assertIn("https://github.com/aruc-dev/HawksCapitol.git", text)
        self.assertIn('branch}" != "main"', text)
        self.assertIn('"mode"', text)
        self.assertIn("git ls-files", text)
        self.assertIn("HAWKSCAPITOL_DRY_RUN=1 scripts/fetch_secrets.sh", text)
        self.assertIn("scripts/validate_terraform.sh", text)
        self.assertIn("python3 -m unittest discover -v", text)
        self.assertIn("git diff --check", text)
        self.assertIn("scheduler/run_live_promotion_check.py", text)
        for script in SCHEDULED_JOBS.values():
            self.assertIn(script, text)

    def test_runtime_outputs_are_gitignored(self) -> None:
        text = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8")

        for path in (
            "data/canonical/",
            "data/paper_broker/",
            "data/signals/",
            "data/trade_log.json",
            "reports/alerts/",
            "reports/daily/",
            "reports/weekly/",
            ".terraform/",
            "*.tfstate",
            "*.tfplan",
            "infra/terraform/terraform.tfvars",
        ):
            self.assertIn(path, text)


if __name__ == "__main__":
    unittest.main()
