#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

if ! command -v terraform >/dev/null 2>&1; then
  echo "terraform not installed; skipping terraform fmt/validate"
  exit 0
fi

terraform -chdir=infra/terraform fmt -check
terraform -chdir=infra/terraform init -backend=false
terraform -chdir=infra/terraform validate
