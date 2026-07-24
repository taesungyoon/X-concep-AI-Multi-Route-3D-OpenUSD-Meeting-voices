#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
PYTHON_BIN="${PYTHON_BIN:-python3}"
PYTORCH_INDEX_URL="${PYTORCH_INDEX_URL:-https://download.pytorch.org/whl/cu128}"
"$PYTHON_BIN" -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip wheel
python -m pip install torch torchvision --index-url "$PYTORCH_INDEX_URL"
python -m pip install -e ".[train,test]"
if [ -f bundle-manifest.json ]; then
  python scripts/verify_install.py
fi
python scripts/check_server.py
python scripts/validate_dataset.py --dataset data/examples
python -m pip freeze > environment.freeze.txt
echo "Installation complete. Activate with: source .venv/bin/activate"
