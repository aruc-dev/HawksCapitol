# HawksCapitol Terraform Deployment

This Terraform root module provisions the paper AWS runtime for HawksCapitol:

- dedicated VPC, public subnet, internet gateway, and route table;
- EC2 security group with no inbound access by default;
- Amazon Linux 2023 EC2 instance with IMDSv2 required;
- IAM role/profile with read-only access to the HawksCapitol paper secret;
- optional Secrets Manager metadata for `hawkscapitol/keys`;
- cloud-init bootstrap that installs Python, clones `origin/main`, installs systemd
  units, runs safe dry-runs, and enables timers.

Terraform does not manage secret values. Secret values must be written outside Terraform
by putting paper credential values into AWS Secrets Manager so keys do not enter local
state or CI logs.

## Local Laptop Flow

```bash
cd infra/terraform
cp terraform.tfvars.example terraform.tfvars
terraform init
terraform plan
terraform apply
```

After the first apply, write paper secret values:

```bash
aws secretsmanager put-secret-value \
  --secret-id hawkscapitol/keys \
  --secret-string '{"ALPACA_API_KEY":"...","ALPACA_SECRET_KEY":"..."}'
```

Then set `enable_systemd_timers = true` in `terraform.tfvars` and apply again.

Use the output command for SSM access:

```bash
terraform output -raw ssm_connect_command
```

## GitHub Actions Flow

Use `.github/workflows/terraform-deploy.yml` after bootstrapping:

1. Create an AWS IAM role trusted by GitHub Actions OIDC for this repository.
2. Create an encrypted S3 backend bucket and DynamoDB lock table.
3. Add repository variables:
   - `AWS_REGION`
   - `AWS_ROLE_TO_ASSUME`
   - `TF_STATE_BUCKET`
   - `TF_STATE_LOCK_TABLE`
4. Run the workflow manually with `apply=false` for plan-only validation.
5. Run with `apply=true` only after reviewing the plan.

The workflow generates a backend file at runtime; no state backend values or AWS keys are
committed to the repository.

## Validation

Local validation from repo root:

```bash
python3 -m unittest -v tests.test_terraform_deployment tests.test_deploy_artifacts
git diff --check
```

If Terraform is installed:

```bash
terraform -chdir=infra/terraform fmt -check
terraform -chdir=infra/terraform init -backend=false
terraform -chdir=infra/terraform validate
```
