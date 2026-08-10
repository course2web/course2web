#!/usr/bin/env bash

set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
java_dir="$(cd "${script_dir}/.." && pwd)"
# shellcheck source=pipeline-common.sh
source "${script_dir}/pipeline-common.sh"

config_file="${PIPELINE_CONFIG_FILE:-${java_dir}/pipeline.env}"
if [[ "${1:-}" == "--config" ]]; then
  [[ -n "${2:-}" ]] || die "--config requires a file"
  config_file="$2"
fi
load_pipeline_config "${config_file}"

aws_region="${AWS_REGION:-us-east-1}"
s3_bucket="${S3_BUCKET:-www.catholicpatrimony.com}"
baseline_dir="${BASELINE_DIR:-./runtime/baseline}"
state_dir="${STATE_DIR:-./runtime/state}"
active_series="${ACTIVE_SERIES:-daily_homilies,misc,st_joseph_novena,magnificat_humanitas}"
if [[ "${baseline_dir}" != /* ]]; then
  baseline_dir="${java_dir}/${baseline_dir#./}"
fi
if [[ "${state_dir}" != /* ]]; then
  state_dir="${java_dir}/${state_dir#./}"
fi

mkdir -p "${baseline_dir}"
temporary_dir="$(mktemp -d "${baseline_dir}/.capture.XXXXXX")"
trap 'rm -rf "${temporary_dir}"' EXIT

safe_aws_cp() {
  assert_safe_aws_s3_args "$@"
  aws s3 cp "$@"
}

safe_aws_cp "s3://${s3_bucket}/cp.json" "${temporary_dir}/cp.json" \
  --region "${aws_region}" --only-show-errors

IFS=',' read -r -a series_names <<< "${active_series}"
for series in "${series_names[@]}"; do
  series="$(trim_space "${series}")"
  [[ -n "${series}" ]] || continue
  mkdir -p "${temporary_dir}/${series}"
  for filename in podcast.xml podcast-2.xml; do
    safe_aws_cp "s3://${s3_bucket}/${series}/${filename}" \
      "${temporary_dir}/${series}/${filename}" \
      --region "${aws_region}" --only-show-errors
  done
done

# Preserve the previous local snapshot before replacing it. These are local,
# small XML/JSON files; this operation never changes S3.
if [[ -f "${baseline_dir}/cp.json" ]]; then
  snapshot_timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
  snapshot_dir="${state_dir}/snapshots/${snapshot_timestamp}"
  mkdir -p "${snapshot_dir}"
  cp -R "${baseline_dir}/." "${snapshot_dir}/"
fi

# Replace only the local snapshot files after every download succeeded.
cp "${temporary_dir}/cp.json" "${baseline_dir}/cp.json"
for series in "${series_names[@]}"; do
  series="$(trim_space "${series}")"
  [[ -n "${series}" ]] || continue
  mkdir -p "${baseline_dir}/${series}"
  cp "${temporary_dir}/${series}/podcast.xml" "${baseline_dir}/${series}/podcast.xml"
  cp "${temporary_dir}/${series}/podcast-2.xml" "${baseline_dir}/${series}/podcast-2.xml"
done

printf 'baseline_dir=%s\n' "${baseline_dir}"
printf 'remote_writes=0\n'
