from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

REQUIRED_FILES = {
    ".env.example",
    "compose.yaml",
    "Dockerfile",
    "pyproject.toml",
    "README.md",
    "SERVER_INSTALL_QUICKSTART_KO.md",
    "configs/qwen3-vl-4b-qlora.json",
    "scripts/import_php_cad_dataset.py",
    "scripts/preprocess_dataset.py",
    "scripts/train_vlm.py",
    "scripts/train.sh",
    "scripts/train.ps1",
    "scripts/validate_dataset.py",
    "src/xconcep_cad_vlm/php_cad.py",
    "data/examples/records.jsonl",
}


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify an extracted Xconcep CAD VLM portable bundle")
    parser.add_argument("--root", default=str(Path(__file__).resolve().parents[1]))
    args = parser.parse_args()
    root = Path(args.root).expanduser().resolve()
    manifest_path = root / "bundle-manifest.json"
    if not manifest_path.exists():
        print(json.dumps({"valid": False, "error": "bundle-manifest.json is missing"}, indent=2))
        return 2
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    failures = []
    rows = manifest.get("files") or []
    listed = {str(row.get("path") or "") for row in rows}
    if manifest.get("schema") != "xconcep.cad-vlm-portable-manifest/1.1":
        failures.append({"path": "bundle-manifest.json", "error": "unsupported schema"})
    for required in sorted(REQUIRED_FILES - listed):
        failures.append({"path": required, "error": "required file is not listed"})
    for row in rows:
        relative = Path(str(row["path"]))
        path = (root / relative).resolve()
        try:
            path.relative_to(root)
        except ValueError:
            failures.append({"path": str(relative), "error": "path traversal"})
            continue
        if not path.is_file():
            failures.append({"path": str(relative), "error": "missing"})
            continue
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != row.get("sha256") or path.stat().st_size != int(row.get("size") or -1):
            failures.append({"path": str(relative), "error": "hash or size mismatch"})
    report = {
        "schema": manifest.get("schema"),
        "valid": not failures,
        "checked_files": len(rows),
        "failures": failures,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["valid"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
