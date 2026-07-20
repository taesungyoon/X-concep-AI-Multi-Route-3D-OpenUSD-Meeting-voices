#!/usr/bin/env bash
set -euo pipefail
: "${GEMMA_MODEL_PATH:?GEMMA_MODEL_PATH is required}"
vllm serve "$GEMMA_MODEL_PATH" \
  --served-model-name "${GEMMA_MODEL_NAME:-gemma-4-64b-local}" \
  --distributed-executor-backend ray \
  --tensor-parallel-size "${VLLM_TP_SIZE:-4}" \
  --pipeline-parallel-size "${VLLM_PP_SIZE:-1}" \
  --host 0.0.0.0 --port "${VLLM_PORT:-8000}" \
  --trust-remote-code
