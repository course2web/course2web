#!/usr/bin/env bash

set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/pipeline-common.sh
source "${script_dir}/scripts/pipeline-common.sh"

print_usage() {
  cat <<'EOF'
Usage: ./go.sh [options]

Options:
  --mode MODE                 dry-run, process, or publish
  --process-not-before DATE   Earliest eligible date (YYYY-MM-DD)
  --config FILE               Optional pipeline environment file
  --allow-publish             Required in addition to publish mode
  --help                      Show this help

Phase 1 intentionally enables configuration validation only. Processing and
publishing are added in Phase 2 after the current behavior is captured by tests.
EOF
}

config_file="${PIPELINE_CONFIG_FILE:-${script_dir}/pipeline.env}"
declare -a cli_args=("$@")

# Find the config path before loading values. Other CLI arguments are applied
# afterward and therefore take precedence over the file.
arg_index=0
while ((arg_index < ${#cli_args[@]})); do
  if [[ "${cli_args[$arg_index]}" == "--config" ]]; then
    ((arg_index + 1 < ${#cli_args[@]})) || die "--config requires a file"
    config_file="${cli_args[$((arg_index + 1))]}"
    ((arg_index += 2))
  else
    ((arg_index += 1))
  fi
done

load_pipeline_config "${config_file}"

run_mode="${RUN_MODE:-dry-run}"
process_not_before="${PROCESS_NOT_BEFORE:-2026-08-04}"
allow_publish="${ALLOW_PUBLISH:-false}"

arg_index=0
while ((arg_index < ${#cli_args[@]})); do
  case "${cli_args[$arg_index]}" in
    --mode)
      ((arg_index + 1 < ${#cli_args[@]})) || die "--mode requires a value"
      run_mode="${cli_args[$((arg_index + 1))]}"
      ((arg_index += 2))
      ;;
    --process-not-before)
      ((arg_index + 1 < ${#cli_args[@]})) || die "--process-not-before requires a date"
      process_not_before="${cli_args[$((arg_index + 1))]}"
      ((arg_index += 2))
      ;;
    --config)
      ((arg_index += 2))
      ;;
    --allow-publish)
      allow_publish="true"
      ((arg_index += 1))
      ;;
    --help|-h)
      print_usage
      exit 0
      ;;
    --delete|--delete-*|delete|rm|rmdir|move|purge|trash)
      die "deletion-capable argument is forbidden: ${cli_args[$arg_index]}"
      ;;
    *)
      die "unknown argument: ${cli_args[$arg_index]}"
      ;;
  esac
done

validate_run_mode "${run_mode}"
validate_iso_date "${process_not_before}"

printf 'run_mode=%s\n' "${run_mode}"
printf 'process_not_before=%s\n' "${process_not_before}"

case "${run_mode}" in
  dry-run)
    printf 'external_writes=disabled\n'
    printf 'status=phase-1-configuration-only\n'
    ;;
  process)
    die "process mode is not enabled until Phase 2"
    ;;
  publish)
    is_true "${allow_publish}" || die "publish mode requires --allow-publish or ALLOW_PUBLISH=true"
    die "publish mode is not enabled until Phase 2"
    ;;
esac
