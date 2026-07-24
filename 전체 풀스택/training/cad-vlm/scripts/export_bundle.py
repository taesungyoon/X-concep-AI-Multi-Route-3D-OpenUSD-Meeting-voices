from __future__ import annotations

import argparse
import hashlib
import json
import zipfile
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
EXCLUDED = {".venv", "outputs", "model-cache", "hf-cache", "dist", "__pycache__", ".pytest_cache"}


def _excluded(path: Path) -> bool:
    relative = path.relative_to(PACKAGE_ROOT)
    if any(part in EXCLUDED for part in relative.parts):
        return True
    return path.name == ".env" or (path.name.startswith(".env.") and path.name != ".env.example")


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a portable Xconcep CAD VLM training bundle")
    parser.add_argument("--output", default=str(PACKAGE_ROOT / "dist" / "xconcep-cad-vlm-portable.zip"))
    args = parser.parse_args()
    output = Path(args.output).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in sorted(PACKAGE_ROOT.rglob("*")):
            if not path.is_file() or _excluded(path):
                continue
            relative = path.relative_to(PACKAGE_ROOT)
            archive.write(path, Path("xconcep-cad-vlm") / relative)
            rows.append({
                "path": relative.as_posix(),
                "size": path.stat().st_size,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            })
        archive.writestr(
            "xconcep-cad-vlm/bundle-manifest.json",
            json.dumps(
                {"schema": "xconcep.cad-vlm-portable-manifest/1.0", "files": rows},
                ensure_ascii=False,
                indent=2,
            ) + "\n",
        )
    digest = hashlib.sha256(output.read_bytes()).hexdigest()
    checksum = output.with_suffix(output.suffix + ".sha256")
    checksum.write_text(f"{digest}  {output.name}\n", encoding="ascii")
    print(f"bundle={output}\nsha256={digest}\nchecksum={checksum}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
