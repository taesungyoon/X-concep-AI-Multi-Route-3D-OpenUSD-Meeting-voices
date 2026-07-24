from __future__ import annotations

import argparse
import hashlib
import json
import zipfile
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
INCLUDED_ROOT_FILES = {
    ".dockerignore",
    ".env.example",
    ".gitignore",
    "compose.yaml",
    "Dockerfile",
    "pyproject.toml",
    "README.md",
    "SERVER_INSTALL_QUICKSTART_KO.md",
}
INCLUDED_DIRS = {"configs", "docs", "schema", "scripts", "src", "tests"}
CANONICAL_EXAMPLE_DIR = Path("data/examples")
EXCLUDED_PARTS = {"__pycache__", ".pytest_cache"}


def _included(path: Path) -> bool:
    """Use an allowlist so caches, user data and temporary builds never leak."""
    relative = path.relative_to(PACKAGE_ROOT)
    if any(part in EXCLUDED_PARTS for part in relative.parts) or path.suffix in {".pyc", ".pyo"}:
        return False
    if len(relative.parts) == 1:
        return relative.name in INCLUDED_ROOT_FILES
    if relative.parts[0] in INCLUDED_DIRS:
        # The one-step PHP smoke config points at a local ephemeral dataset.
        return not (relative.parts[0] == "configs" and "smoke" in relative.name)
    return relative.is_relative_to(CANONICAL_EXAMPLE_DIR)


def _iter_included_files() -> list[Path]:
    """Traverse only approved roots; inaccessible model-cache links are untouched."""
    paths = [PACKAGE_ROOT / name for name in sorted(INCLUDED_ROOT_FILES)]
    for directory in sorted(INCLUDED_DIRS):
        root = PACKAGE_ROOT / directory
        if root.is_dir():
            paths.extend(path for path in root.rglob("*") if path.is_file())
    example_root = PACKAGE_ROOT / CANONICAL_EXAMPLE_DIR
    if example_root.is_dir():
        paths.extend(path for path in example_root.rglob("*") if path.is_file())
    return sorted({path.resolve() for path in paths if path.is_file() and _included(path)})


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a portable Xconcep CAD VLM training bundle")
    parser.add_argument("--output", default=str(PACKAGE_ROOT / "dist" / "xconcep-cad-vlm-portable.zip"))
    args = parser.parse_args()
    output = Path(args.output).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in _iter_included_files():
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
                {
                    "schema": "xconcep.cad-vlm-portable-manifest/1.1",
                    "package": "xconcep-cad-vlm",
                    "purpose": "portable GPU-server installation and DesignSpec fine-tuning",
                    "file_count": len(rows),
                    "files": rows,
                },
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
