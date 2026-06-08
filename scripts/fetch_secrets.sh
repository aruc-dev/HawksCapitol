#!/usr/bin/env bash
set -euo pipefail

secret_id="${HAWKSCAPITOL_SECRET_ID:-hawkscapitol/keys}"
target="${HAWKSCAPITOL_ENV_FILE:-/dev/shm/.hawkscapitol.env}"
require_shm="${HAWKSCAPITOL_REQUIRE_SHM:-0}"
dry_run="${HAWKSCAPITOL_DRY_RUN:-0}"
validate_only="${HAWKSCAPITOL_VALIDATE_ONLY:-0}"
aws_cli="${AWS_CLI:-aws}"

if [[ "${require_shm}" == "1" && "${target}" != /dev/shm/* ]]; then
  echo "refusing to write secrets outside /dev/shm when HAWKSCAPITOL_REQUIRE_SHM=1" >&2
  exit 1
fi

if [[ "${HAWKSCAPITOL_DRY_RUN:-0}" == "1" ]]; then
  echo "dry-run: would fetch AWS Secrets Manager secret '${secret_id}' into '${target}' (values redacted)"
  exit 0
fi

if [[ "${validate_only}" == "1" ]]; then
  if [[ ! -f "${target}" ]]; then
    echo "validation failed: ${target} is missing" >&2
    exit 1
  fi
  mode="$(stat -c '%a' "${target}" 2>/dev/null || stat -f '%Lp' "${target}")"
  if [[ "${mode}" != "600" ]]; then
    echo "validation failed: ${target} permissions are ${mode}, expected 600" >&2
    exit 1
  fi
  echo "validation ok: ${target} exists with 0600 permissions (values redacted)"
  exit 0
fi

if ! command -v "${aws_cli}" >/dev/null 2>&1; then
  echo "aws cli not found; install awscli or set AWS_CLI" >&2
  exit 1
fi

target_dir="$(dirname "${target}")"
mkdir -p "${target_dir}"
umask 077
raw_file="$(mktemp "${target_dir}/.hawkscapitol.secret.raw.XXXXXX")"
env_file="$(mktemp "${target_dir}/.hawkscapitol.env.XXXXXX")"
cleanup() {
  rm -f "${raw_file}" "${env_file}"
}
trap cleanup EXIT

"${aws_cli}" secretsmanager get-secret-value \
  --secret-id "${secret_id}" \
  --query SecretString \
  --output text >"${raw_file}"

python3 - "${raw_file}" "${env_file}" <<'PY'
from __future__ import annotations

import json
import re
import sys

KEY_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def quote_env(value: object) -> str:
    text = str(value)
    text = text.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
    return f'"{text}"'


raw_path, env_path = sys.argv[1], sys.argv[2]
payload = open(raw_path, encoding="utf-8").read()

try:
    decoded = json.loads(payload)
except json.JSONDecodeError:
    decoded = None

lines: list[str] = []
if isinstance(decoded, dict):
    for key in sorted(decoded):
        if decoded[key] is None:
            continue
        key_text = str(key)
        if not KEY_RE.match(key_text):
            raise SystemExit(f"invalid environment key in secret: {key_text}")
        lines.append(f"{key_text}={quote_env(decoded[key])}\n")
else:
    for raw_line in payload.splitlines():
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if "=" not in stripped:
            raise SystemExit("secret must be JSON object or KEY=VALUE lines")
        key, value = stripped.split("=", 1)
        key = key.strip()
        if not KEY_RE.match(key):
            raise SystemExit(f"invalid environment key in secret: {key}")
        lines.append(f"{key}={value.strip()}\n")

if not lines:
    raise SystemExit("secret contains no environment values")

with open(env_path, "w", encoding="utf-8") as handle:
    handle.writelines(lines)
PY

chmod 600 "${env_file}"
mv "${env_file}" "${target}"
rm -f "${raw_file}"
trap - EXIT
echo "populated ${target} from AWS Secrets Manager secret '${secret_id}' (values redacted)"
