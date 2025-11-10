#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export PYTHONPATH="${SCRIPT_DIR}/lib:${SCRIPT_DIR}:${PYTHONPATH:-}"

exec python3 -m opencv_webapp.webapp "$@"
