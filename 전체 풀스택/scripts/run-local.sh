#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python}"
VENV_BIN="${VENV_BIN:-}"
if [[ -n "$VENV_BIN" ]]; then PYTHON_BIN="$VENV_BIN/python"; UVICORN_BIN="$VENV_BIN/uvicorn"; else UVICORN_BIN="uvicorn"; fi
mkdir -p "$ROOT/storage/projects"
rm -rf "$ROOT/frontend-php/public/storage"
ln -s "$ROOT/storage" "$ROOT/frontend-php/public/storage"
rm -f "$ROOT/control-plane-drf/db.sqlite3"

cleanup() {
  for pid in ${PIDS:-}; do kill "$pid" 2>/dev/null || true; done
}
trap cleanup EXIT INT TERM

cd "$ROOT/control-plane-drf"
DB_ENGINE=sqlite STORAGE_PATH="$ROOT/storage" "$PYTHON_BIN" manage.py migrate --noinput

cd "$ROOT/knowledge-service"
QDRANT_URL=:memory: EMBED_MODE=hash NEMO_RETRIEVER_MODE=fallback "$UVICORN_BIN" app.main:app --host 127.0.0.1 --port 8020 & PIDS="$!"
cd "$ROOT/python-worker"
STORAGE_PATH="$ROOT/storage" PUBLIC_STORAGE_PREFIX=/storage PIPELINE_MODE=mock LLM_MODE=mock OPENAI_IMAGE_MODE=mock HUNYUAN_MODE=mock SPEECH_MODE=mock OPENSCAD_MODE=fallback BLENDER_MODE=fallback OPENUSD_GENERATE_USDC=true OMNIVERSE_ENABLED=true "$UVICORN_BIN" app.main:app --host 127.0.0.1 --port 8001 & PIDS="$PIDS $!"
cd "$ROOT/agent-layer-nat"
PYTHON_WORKER_URL=http://127.0.0.1:8001 KNOWLEDGE_SERVICE_URL=http://127.0.0.1:8020 AGENT_RUNTIME=fallback "$UVICORN_BIN" gateway:app --host 127.0.0.1 --port 8010 & PIDS="$PIDS $!"
cd "$ROOT/control-plane-drf"
DB_ENGINE=sqlite STORAGE_PATH="$ROOT/storage" AGENT_GATEWAY_URL=http://127.0.0.1:8010 KNOWLEDGE_SERVICE_URL=http://127.0.0.1:8020 DJANGO_DEBUG=true "$PYTHON_BIN" manage.py runserver 127.0.0.1:8000 --noreload & PIDS="$PIDS $!"
cd "$ROOT"
CONTROL_PLANE_URL=http://127.0.0.1:8000 MAX_UPLOAD_MB=30 php -d max_execution_time=0 -d default_socket_timeout=7200 -S 127.0.0.1:8080 -t frontend-php/public frontend-php/public/router.php & PIDS="$PIDS $!"

echo "UI: http://127.0.0.1:8080"
echo "DRF: http://127.0.0.1:8000/api/system-status"
echo "Python Worker: http://127.0.0.1:8001/docs"
echo "Agent Gateway: http://127.0.0.1:8010/docs"
echo "Knowledge Service: http://127.0.0.1:8020/docs"
wait
