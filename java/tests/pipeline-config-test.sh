#!/usr/bin/env bash

set -euo pipefail

java_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
go_script="${java_dir}/go.sh"

fail() {
  echo "FAIL: $*" >&2
  exit 1
}

output="$("${go_script}" --config-check)"
grep -Fq 'run_mode=dry-run' <<< "${output}" || fail "dry-run must be the default"
grep -Fq 'process_not_before=2026-08-04' <<< "${output}" || fail "cutoff default is missing"
grep -Fq 'external_writes=disabled' <<< "${output}" || fail "dry-run must disable writes"

config_file="$(mktemp)"
trap 'rm -f "${config_file}"' EXIT
printf 'PROCESS_NOT_BEFORE=2026-09-01\nRUN_MODE=dry-run\n' > "${config_file}"
output="$("${go_script}" --config "${config_file}" --process-not-before 2026-10-02 --config-check)"
grep -Fq 'process_not_before=2026-10-02' <<< "${output}" || fail "CLI must override config"

if "${go_script}" --process-not-before 08/04/2026 >/dev/null 2>&1; then
  fail "non-ISO cutoff was accepted"
fi
if "${go_script}" --process-not-before 2026-02-29 >/dev/null 2>&1; then
  fail "impossible calendar date was accepted"
fi
"${go_script}" --process-not-before 2028-02-29 --config-check >/dev/null || fail "valid leap day was rejected"

if "${go_script}" --mode publish >/dev/null 2>&1; then
  fail "publish mode did not require explicit opt-in"
fi

if "${go_script}" --delete >/dev/null 2>&1; then
  fail "deletion-capable argument was accepted"
fi

# shellcheck source=../scripts/pipeline-common.sh
source "${java_dir}/scripts/pipeline-common.sh"
if (assert_safe_aws_s3_args sync --delete 2>/dev/null); then
  fail "AWS --delete was accepted"
fi
if (assert_safe_aws_s3_args s3api delete-object 2>/dev/null); then
  fail "AWS delete-object was accepted"
fi
if (assert_safe_rclone_args sync remote:path local-path 2>/dev/null); then
  fail "rclone sync was accepted"
fi

echo "PASS pipeline configuration and deletion guardrails"
