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
  --config-check              Validate and print configuration without running
  --help                      Show this help
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
config_check="false"

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
    --config-check)
      config_check="true"
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

if [[ "${run_mode}" == "publish" ]]; then
  is_true "${allow_publish}" || die "publish mode requires --allow-publish or ALLOW_PUBLISH=true"
  printf 'external_writes=enabled-after-validation\n'
else
  printf 'external_writes=disabled\n'
fi

if is_true "${config_check}"; then
  printf 'status=configuration-valid\n'
  exit 0
fi

resolve_path() {
  local value="$1"
  if [[ "${value}" == /* ]]; then
    printf '%s' "${value}"
  else
    printf '%s/%s' "${script_dir}" "${value#./}"
  fi
}

work_dir="$(resolve_path "${WORK_DIR:-./runtime/work}")"
state_dir="$(resolve_path "${STATE_DIR:-./runtime/state}")"
baseline_dir="$(resolve_path "${BASELINE_DIR:-./runtime/baseline}")"
input_mode="${INPUT_MODE:-local}"
input_root="${INPUT_ROOT:-}"

pipeline_args=(
  --mode "${run_mode}"
  --process-not-before "${process_not_before}"
  --work-dir "${work_dir}"
  --state-dir "${state_dir}"
  --baseline-dir "${baseline_dir}"
  --input-mode "${input_mode}"
  --rclone-remote "${GOOGLE_DRIVE_REMOTE:-course2web-drive}"
  --rclone-uploads-path "${GOOGLE_DRIVE_UPLOADS_PATH:-My Drive/catholic/tedesche/uploads}"
  --active-series "${ACTIVE_SERIES:-daily_homilies,misc,st_joseph_novena,magnificat_humanitas}"
  --s3-bucket "${S3_BUCKET:-www.catholicpatrimony.com}"
  --aws-region "${AWS_REGION:-us-east-1}"
  --cloudfront-distribution-id "${CLOUDFRONT_DISTRIBUTION_ID:-}"
)

if [[ "${input_mode}" == "local" ]]; then
  [[ -n "${input_root}" ]] || die "INPUT_ROOT is required when INPUT_MODE=local"
  pipeline_args+=(--input-root "$(resolve_path "${input_root}")")
fi
if is_true "${CHECK_AWS:-false}"; then
  pipeline_args+=(--check-aws)
fi
if [[ "${run_mode}" == "publish" ]]; then
  pipeline_args+=(--allow-publish)
fi

exec python3 "${script_dir}/pipeline.py" "${pipeline_args[@]}"
