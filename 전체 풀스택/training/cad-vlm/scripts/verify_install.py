from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


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
    for row in manifest.get("files") or []:
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
        "checked_files": len(manifest.get("files") or []),
        "failures": failures,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["valid"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
