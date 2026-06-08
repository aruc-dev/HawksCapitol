#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

normalize_github_remote() {
  local remote_url="$1"
  local remote_path="${remote_url}"
  case "${remote_url}" in
    https://github.com/*)
      remote_path="${remote_url#https://github.com/}"
      ;;
    git@github.com:*)
      remote_path="${remote_url#git@github.com:}"
      ;;
    ssh://git@github.com/*)
      remote_path="${remote_url#ssh://git@github.com/}"
      ;;
  esac
  remote_path="${remote_path%/}"
  remote_path="${remote_path%.git}"
  printf '%s\n' "${remote_path}"
}

expected_remote_slug="aruc-dev/HawksCapitol"
actual_remote="$(git remote get-url origin)"
actual_remote_slug="$(normalize_github_remote "${actual_remote}")"
branch="$(git branch --show-current)"

if [[ "${actual_remote_slug}" != "${expected_remote_slug}" ]]; then
  echo "unexpected origin remote: ${actual_remote}" >&2
  exit 1
fi

if [[ "${branch}" != "main" ]]; then
  echo "paper deployment readiness must be checked from main; current branch is ${branch}" >&2
  exit 1
fi

mode="$(python3 - <<'PY'
from core.config_loader import load_config

print(load_config()["mode"])
PY
)"
if [[ "${mode}" != "paper" ]]; then
  echo "refusing paper deploy readiness with mode=${mode}" >&2
  exit 1
fi

if git ls-files | grep -E '(^|/)(\.env|[^/]+\.pem)$' >/dev/null; then
  echo "tracked secret-like files found; refusing deploy readiness" >&2
  git ls-files | grep -E '(^|/)(\.env|[^/]+\.pem)$' >&2
  exit 1
fi

bash -n scripts/fetch_secrets.sh
scripts/validate_terraform.sh
HAWKSCAPITOL_DRY_RUN=1 scripts/fetch_secrets.sh >/dev/null
python3 -m unittest discover -v

for runner in \
  scheduler/run_ingest.py \
  scheduler/run_score.py \
  scheduler/run_scan.py \
  scheduler/run_risk_check.py \
  scheduler/run_report.py \
  scheduler/run_weekly_report.py \
  scheduler/run_health_check.py \
  scheduler/run_live_promotion_check.py
do
  python3 "${runner}" --dry-run >/dev/null
done

git diff --check
echo "paper deploy readiness ok for origin/main (remote systemd validation still required on HCEC2P)"
