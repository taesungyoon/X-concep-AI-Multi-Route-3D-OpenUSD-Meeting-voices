#!/usr/bin/env bash
set -euo pipefail
MODEL_PATH="${GEMMA_MODEL_PATH:?GEMMA_MODEL_PATH is required}"
SERVED_NAME="${GEMMA_SERVED_MODEL_NAME:-gemma-4-64b-local}"
TP="${VLLM_TP_SIZE:-4}"
PP="${VLLM_PP_SIZE:-2}"
MAX_LEN="${VLLM_MAX_MODEL_LEN:-32768}"
PORT="${VLLM_PORT:-8000}"
GPU_UTIL="${VLLM_GPU_MEMORY_UTILIZATION:-0.90}"

vllm serve "$MODEL_PATH" \
  --served-model-name "$SERVED_NAME" \
  --host 0.0.0.0 \
  --port "$PORT" \
  --tensor-parallel-size "$TP" \
  --pipeline-parallel-size "$PP" \
  --distributed-executor-backend ray \
  --max-model-len "$MAX_LEN" \
  --gpu-memory-utilization "$GPU_UTIL" \
  --trust-remote-code \
  "${@}"
