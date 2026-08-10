#!/usr/bin/env bash

set -euo pipefail

java_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
repo_dir="$(cd "${java_dir}/.." && pwd)"
expected_file="${java_dir}/tests/fixtures/current-behavior.json"
cp_file="${repo_dir}/web/cp.json"
backend_file="${java_dir}/src/BackendIngestorAndTransformer.groovy"
podcast_template="${java_dir}/velocity/podcast.vm"

command -v jq >/dev/null || { echo "jq is required" >&2; exit 1; }

first_line="$(sed -n '1p' "${cp_file}")"
expected_prefix="$(jq -r '.cpJson.assignmentPrefix' "${expected_file}")"
[[ "${first_line}" == "${expected_prefix}[" ]] || {
  echo "cp.json assignment prefix changed" >&2
  exit 1
}

actual_json="$(mktemp)"
trap 'rm -f "${actual_json}"' EXIT
sed '1s/^cp = //' "${cp_file}" > "${actual_json}"
jq empty "${actual_json}"

actual_summary="$({
  jq '{
    seriesCount: length,
    classCount: (map(.classes | length) | add),
    audioClassCount: ([.[].classes[] | select(.audio != null)] | length),
    linkedAudioClassCount: ([.[].classes[] | select(.link2mp3 != null)] | length),
    seriesNames: map(.seriesData.normalized_name)
  }' "${actual_json}"
})"
expected_summary="$(jq '.cpJson | del(.assignmentPrefix)' "${expected_file}")"
jq -e --argjson actual "${actual_summary}" --argjson expected "${expected_summary}" \
  '$actual == $expected' <<< '{}' >/dev/null || {
    echo "cp.json behavior differs from the captured baseline" >&2
    diff -u <(printf '%s\n' "${expected_summary}") <(printf '%s\n' "${actual_summary}") || true
    exit 1
  }

grep -Fq '#if( $foreach.count > 50 )' "${podcast_template}"
grep -Fq '<guid>http://www.catholicpatrimony.com$class.link2mp3</guid>' "${podcast_template}"
grep -Fq 'if (new File(newFile).exists())' "${backend_file}"
grep -Fq 'podcast-2.xml' "${backend_file}"

echo "PASS current cp.json and podcast behavior matches the captured gh-pages baseline"
