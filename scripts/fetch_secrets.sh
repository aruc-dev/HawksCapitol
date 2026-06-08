#!/usr/bin/env bash
set -euo pipefail

target="${HAWKSCAPITOL_ENV_FILE:-/dev/shm/.hawkscapitol.env}"
if [[ "${HAWKSCAPITOL_DRY_RUN:-0}" == "1" ]]; then
  echo "dry-run: would populate ${target}"
  exit 0
fi

echo "This scaffold requires AWS Secrets Manager integration before production use." >&2
exit 1
