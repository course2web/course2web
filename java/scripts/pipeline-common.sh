#!/usr/bin/env bash

# Shared safety and configuration helpers for the EC2 processing pipeline.
# This file deliberately contains no external service calls.

die() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 2
}

is_true() {
  case "${1:-}" in
    true|TRUE|yes|YES|1) return 0 ;;
    *) return 1 ;;
  esac
}

validate_run_mode() {
  case "${1:-}" in
    dry-run|process|publish) ;;
    *) die "invalid run mode '${1:-}'; expected dry-run, process, or publish" ;;
  esac
}

validate_iso_date() {
  local value="${1:-}"
  if [[ ! "${value}" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}$ ]]; then
    die "invalid date '${value}'; expected YYYY-MM-DD"
  fi

  # ISO dates compare lexically, but reject impossible calendar values first.
  local year="${value:0:4}"
  local month="${value:5:2}"
  local day="${value:8:2}"
  local year_number=$((10#${year}))
  local month_number=$((10#${month}))
  local day_number=$((10#${day}))
  local maximum_day

  case "${month_number}" in
    1|3|5|7|8|10|12) maximum_day=31 ;;
    4|6|9|11) maximum_day=30 ;;
    2)
      maximum_day=28
      if ((year_number % 400 == 0 || (year_number % 4 == 0 && year_number % 100 != 0))); then
        maximum_day=29
      fi
      ;;
    *) die "invalid calendar date '${value}'" ;;
  esac

  if ((day_number < 1 || day_number > maximum_day)); then
    die "invalid calendar date '${value}'"
  fi
}

is_allowed_config_key() {
  case "${1:-}" in
    RUN_MODE|PROCESS_NOT_BEFORE|ALLOW_PUBLISH|AWS_REGION|S3_BUCKET|CLOUDFRONT_DISTRIBUTION_ID|GOOGLE_DRIVE_REMOTE|GOOGLE_DRIVE_UPLOADS_PATH)
      return 0
      ;;
    *)
      return 1
      ;;
  esac
}

trim_space() {
  local value="${1:-}"
  value="${value#"${value%%[![:space:]]*}"}"
  value="${value%"${value##*[![:space:]]}"}"
  printf '%s' "${value}"
}

load_pipeline_config() {
  local config_file="${1:-}"
  [[ -n "${config_file}" ]] || return 0
  [[ -e "${config_file}" ]] || return 0
  [[ -f "${config_file}" ]] || die "config path is not a regular file: ${config_file}"

  local raw_line key value
  while IFS= read -r raw_line || [[ -n "${raw_line}" ]]; do
    raw_line="$(trim_space "${raw_line}")"
    [[ -z "${raw_line}" || "${raw_line}" == \#* ]] && continue
    [[ "${raw_line}" == *=* ]] || die "invalid config line in ${config_file}: ${raw_line}"

    key="$(trim_space "${raw_line%%=*}")"
    value="$(trim_space "${raw_line#*=}")"
    is_allowed_config_key "${key}" || die "unsupported config key '${key}' in ${config_file}"

    # Existing environment values win over the file; CLI values are applied later.
    if [[ ! -v "${key}" ]]; then
      printf -v "${key}" '%s' "${value}"
      export "${key}"
    fi
  done < "${config_file}"
}

assert_safe_aws_s3_args() {
  local arg
  for arg in "$@"; do
    case "${arg}" in
      --delete|--delete-*|delete|delete-*|rm|mv)
        die "forbidden AWS S3 deletion/move argument: ${arg}"
        ;;
    esac
  done
}

assert_safe_rclone_args() {
  local arg
  for arg in "$@"; do
    case "${arg}" in
      sync|move|moveto|delete|deletefile|purge|cleanup|rmdirs|--delete-*|--track-renames)
        die "forbidden rclone deletion/move argument: ${arg}"
        ;;
    esac
  done
}
