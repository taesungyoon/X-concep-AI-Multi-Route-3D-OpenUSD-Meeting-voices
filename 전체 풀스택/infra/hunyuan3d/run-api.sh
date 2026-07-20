#!/usr/bin/env bash
set -euo pipefail
INSTALL_DIR="${HUNYUAN_INSTALL_DIR:-$HOME/Hunyuan3D-2.1}"
PORT="${HUNYUAN_PORT:-8081}"
cd "$INSTALL_DIR"
source .venv/bin/activate
python api_server.py --host 0.0.0.0 --port "$PORT"
