#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
CONFIG="${1:-configs/qwen3-vl-4b-qlora.json}"
GPU_COUNT="${GPU_COUNT:-1}"
. .venv/bin/activate
python scripts/train_vlm.py --config "$CONFIG" --dry-run
if [ "$GPU_COUNT" -gt 1 ]; then
  export WORLD_SIZE="$GPU_COUNT"
  accelerate launch --num_processes "$GPU_COUNT" scripts/train_vlm.py --config "$CONFIG"
else
  export WORLD_SIZE=1
  python scripts/train_vlm.py --config "$CONFIG"
fi

