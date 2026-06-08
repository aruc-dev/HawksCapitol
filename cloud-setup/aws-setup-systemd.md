# HawksCapitol AWS Deployment

HawksCapitol uses Terraform as the primary AWS deployment path. The paper EC2 host
(`HCEC2P`) should be provisioned from `infra/terraform` from a laptop now and, after
remote state/OIDC bootstrap, from GitHub Actions.

This document does not authorize live trading. Keep `config/config.yaml` at
`"mode": "paper"` unless a human explicitly approves live mode in the current session.

## Terraform First

Local laptop flow:

```bash
cd infra/terraform
cp terraform.tfvars.example terraform.tfvars
terraform init
terraform plan
terraform apply
```

Terraform provisions:

- VPC, public subnet, route table, and security group;
- Amazon Linux 2023 EC2 paper node;
- EC2 IAM role/profile with SSM Session Manager access;
- read-only Secrets Manager access scoped to `hawkscapitol/keys`;
- optional Secrets Manager metadata only;
- cloud-init bootstrap that clones `origin/main`, installs Python dependencies,
  installs `hawkscapitol-*` systemd units, and runs safe dry-runs.

Terraform intentionally does not manage secret values. Secret values must be written
through AWS Secrets Manager outside Terraform so credentials do not enter local state,
remote state, GitHub Actions logs, or plan output.

After the first apply, write paper credentials:

```bash
aws secretsmanager put-secret-value \
  --secret-id hawkscapitol/keys \
  --secret-string '{"ALPACA_API_KEY":"...","ALPACA_SECRET_KEY":"..."}'
```

Then set `enable_systemd_timers = true` in `infra/terraform/terraform.tfvars` and apply
again.

Connect with SSM using the Terraform output:

```bash
terraform -chdir=infra/terraform output -raw ssm_connect_command
```

## GitHub Actions Path

`.github/workflows/terraform-deploy.yml` is ready for a later GitHub Actions deployment
flow. Before enabling apply from Actions:

1. Create an AWS IAM role trusted by GitHub Actions OIDC for this repository.
2. Create an encrypted S3 state bucket and DynamoDB lock table.
3. Add repository variables `AWS_REGION`, `AWS_ROLE_TO_ASSUME`, `TF_STATE_BUCKET`, and
   `TF_STATE_LOCK_TABLE`.
4. Run the workflow manually with `apply=false` and review the plan.
5. Run with `apply=true` only after review.

No static AWS access keys are required by the workflow.

## IAM

Terraform creates an instance role with least-privilege read access to the HawksCapitol
paper secret only:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": ["secretsmanager:GetSecretValue"],
      "Resource": "arn:aws:secretsmanager:REGION:ACCOUNT_ID:secret:hawkscapitol/keys-*"
    }
  ]
}
```

Do not attach write permissions, wildcard service permissions, or unrelated secret
access.

## Secret

Terraform can create metadata for `hawkscapitol/keys` in AWS Secrets Manager. The
secret value must be a JSON object. Expected keys are environment variable names
consumed by the app, for example Alpaca paper credentials.

Do not store live credentials in the paper secret. Do not print the secret contents in
shell history, logs, or Beads notes.

## Manual Host Install Fallback

Terraform user data performs this setup automatically. Use these commands only for
troubleshooting or a manual rebuild on an already provisioned host:

```bash
sudo dnf update -y
sudo dnf install -y git python3 python3-pip python3-virtualenv awscli
sudo -u ec2-user git clone https://github.com/aruc-dev/HawksCapitol.git /home/ec2-user/HawksCapitol
cd /home/ec2-user/HawksCapitol
sudo chown -R ec2-user:ec2-user /home/ec2-user/HawksCapitol
sudo -u ec2-user python3 -m venv .venv
. .venv/bin/activate
sudo -u ec2-user .venv/bin/pip install -r requirements.txt
sudo -u ec2-user .venv/bin/python -m unittest discover -v
sudo -u ec2-user .venv/bin/python scheduler/run_health_check.py --dry-run
```

Verify the remote is the approved repository before deploying:

```bash
git remote -v
git branch --show-current
git rev-parse --short HEAD
```

Deploy only approved `origin/main` for paper EC2 unless the human explicitly approves a
different ref in-session.

## Secrets Materialization

The systemd secrets service writes AWS Secrets Manager `hawkscapitol/keys` to tmpfs:

```bash
HAWKSCAPITOL_DRY_RUN=1 scripts/fetch_secrets.sh
sudo -u ec2-user HAWKSCAPITOL_REQUIRE_SHM=1 scripts/fetch_secrets.sh
sudo -u ec2-user HAWKSCAPITOL_VALIDATE_ONLY=1 scripts/fetch_secrets.sh
```

Expected target: `/dev/shm/.hawkscapitol.env` with `0600` permissions. The script logs
only paths and secret IDs, never secret values.

## Manual systemd Install Fallback

Terraform user data installs the systemd units. Use this manually only if refreshing
units on an existing host:

```bash
sudo cp scheduler/systemd/hawkscapitol-*.service /etc/systemd/system/
sudo cp scheduler/systemd/hawkscapitol-*.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now hawkscapitol-secrets.service
sudo systemctl enable --now hawkscapitol-ingest.timer
sudo systemctl enable --now hawkscapitol-score.timer
sudo systemctl enable --now hawkscapitol-scan.timer
sudo systemctl enable --now hawkscapitol-risk-check.timer
sudo systemctl enable --now hawkscapitol-daily-report.timer
sudo systemctl enable --now hawkscapitol-weekly-report.timer
sudo systemctl enable --now hawkscapitol-health-check.timer
```

## Paper Validation

Run these before closing any remote deployment bead:

```bash
scripts/validate_terraform.sh
systemctl list-timers 'hawkscapitol-*'
systemctl status hawkscapitol-secrets.service --no-pager
sudo -u ec2-user HAWKSCAPITOL_VALIDATE_ONLY=1 /home/ec2-user/HawksCapitol/scripts/fetch_secrets.sh
cd /home/ec2-user/HawksCapitol
python3 -m unittest discover -v
python3 scheduler/run_ingest.py --dry-run
python3 scheduler/run_score.py --dry-run
python3 scheduler/run_scan.py --dry-run
python3 scheduler/run_risk_check.py --dry-run
python3 scheduler/run_report.py --dry-run
python3 scheduler/run_weekly_report.py --dry-run
python3 scheduler/run_health_check.py --dry-run
journalctl -u 'hawkscapitol-*' --since '30 minutes ago' --no-pager
```

After enabling timers on `HCEC2P`, monitor for at least 10 minutes:

```bash
watch -n 60 "systemctl list-timers 'hawkscapitol-*'; journalctl -u 'hawkscapitol-*' --since '15 minutes ago' --no-pager | tail -80"
```

Close the deployment bead only when Terraform apply is reviewed, timers are active,
dry-runs are green, health is green, and `journalctl` shows no new errors.

## Development Parity

`cron/hawkscapitol.crontab` and `launchd/com.hawkscapitol.*.plist` mirror the same
scheduler entrypoints for local development. Replace `/path/to/HawksCapitol` before
loading them locally. Production paper uses systemd only.
