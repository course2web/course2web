#!/usr/bin/env bash

set -euo pipefail

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Run this installer as root (for example, sudo $0)." >&2
  exit 2
fi

if [[ ! -r /etc/os-release ]]; then
  echo "Cannot identify this operating system." >&2
  exit 2
fi
# shellcheck source=/etc/os-release
source /etc/os-release
if [[ "${ID:-}" != "debian" || "${VERSION_ID:-}" != "13" ]]; then
  echo "This installer is pinned to Debian 13; found ${PRETTY_NAME:-unknown}." >&2
  exit 2
fi

apt-get update
DEBIAN_FRONTEND=noninteractive apt-get install -y \
  ca-certificates \
  ffmpeg \
  git \
  jq \
  python3 \
  rclone \
  rsync \
  unzip \
  zip

# YouTube changes frequently. Debian backports provides a newer maintained
# yt-dlp while retaining Debian package verification and ARM64 support.
DEBIAN_FRONTEND=noninteractive apt-get install -y -t trixie-backports yt-dlp

for tool in aws ffmpeg ffprobe git jq python3 rclone yt-dlp; do
  command -v "${tool}" >/dev/null || {
    echo "Required tool missing after installation: ${tool}" >&2
    exit 1
  }
done

echo "Course2Web dependencies installed successfully."
