#!/usr/bin/env bash
set -euo pipefail
INSTALL_DIR="${HUNYUAN_INSTALL_DIR:-$HOME/Hunyuan3D-2.1}"
if [[ ! -d "$INSTALL_DIR/.git" ]]; then
  git clone https://github.com/Tencent-Hunyuan/Hunyuan3D-2.1.git "$INSTALL_DIR"
fi
cd "$INSTALL_DIR"
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
printf '\nInstalled at %s\nReview the repository license before commercial deployment.\n' "$INSTALL_DIR"
