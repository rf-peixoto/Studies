#!/usr/bin/env bash
# scan.sh - Simple scan launcher. It only receives a domains file and passes it to Docker.

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec "$SCRIPT_DIR/start.sh" "$@"
