#!/usr/bin/env bash

set -euo pipefail

tests_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

"${tests_dir}/current-behavior-test.sh"
"${tests_dir}/pipeline-config-test.sh"
