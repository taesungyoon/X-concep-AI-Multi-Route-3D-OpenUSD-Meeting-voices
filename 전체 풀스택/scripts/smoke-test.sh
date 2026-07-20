#!/usr/bin/env bash
set -euo pipefail
BASE="${BASE_URL:-http://127.0.0.1:8080}"
API_BASE="${API_BASE_URL:-$BASE}"
PROMPT="${SMOKE_PROMPT:-알루미늄 프레임 구조의 산업용 비전 검사 모듈, 상부 카메라와 컨베이어 및 투명 안전커버 포함}"
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
curl -fsS "$BASE/health" > "$TMP/web.json"
curl -fsS "$API_BASE/api/system-status" > "$TMP/status.json"
curl -fsS -X POST "$API_BASE/api/projects" -F "prompt=$PROMPT" -F 'category=module' -F 'output_goal=auto' -F 'quality_profile=standard' > "$TMP/create.json"
python - "$TMP" <<'PY2'
import json, pathlib, sys
p=pathlib.Path(sys.argv[1]); j=json.load(open(p/'create.json')); pr=j['project']; cs=pr['results_2d']
assert pr['status']=='2d_ready' and len(cs)==4
(p/'pid').write_text(pr['id']); (p/'cid').write_text(cs[0]['id'])
print('2D PASS',pr['id'],len(cs))
PY2
PID=$(cat "$TMP/pid"); CID=$(cat "$TMP/cid")
PAYLOAD=$(printf '{"selected_2d_id":"%s","output_goal":"auto","quality_profile":"standard"}' "$CID")
curl -fsS -X POST "$API_BASE/api/projects/$PID/generate-3d" -H 'Content-Type: application/json' -d "$PAYLOAD" > "$TMP/result.json"
python - "$TMP" <<'PY2'
import json, pathlib, sys
p=pathlib.Path(sys.argv[1]); pr=json.load(open(p/'result.json'))['project']; r=pr['result_3d']
assert pr['status']=='completed'; assert {'fast','structural','high_quality'} <= set(r['assets'])
assert r['validation_grade'] in {'structured','validated','engineer_reviewed','manufacturing_approved'}
print('3D PASS',r['active_asset'],r['validation_grade'],r['validation']['score'])
print('OpenUSD',r.get('openusd_root_url'))
PY2
