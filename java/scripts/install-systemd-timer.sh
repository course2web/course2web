#!/usr/bin/env bash

set -euo pipefail

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run this installer with sudo." >&2
  exit 1
fi

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
java_dir="$(cd "${script_dir}/.." && pwd)"

install -m 0644 "${java_dir}/systemd/course2web-pipeline.service" \
  /etc/systemd/system/course2web-pipeline.service
install -m 0644 "${java_dir}/systemd/course2web-pipeline.timer" \
  /etc/systemd/system/course2web-pipeline.timer

systemctl daemon-reload
systemctl enable --now course2web-pipeline.timer

systemctl --no-pager status course2web-pipeline.timer
