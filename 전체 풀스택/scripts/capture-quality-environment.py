from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


STACK_ROOT = Path(__file__).resolve().parents[1]
WORKER_ROOT = STACK_ROOT / "python-worker"
sys.path.insert(0, str(WORKER_ROOT))

from app.settings import get_settings  # noqa: E402


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _version(name: str) -> str | None:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return None


def _command_version(command: list[str]) -> dict[str, Any]:
    try:
        completed = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30, check=False)
        text = (completed.stdout or completed.stderr).strip().splitlines()
        return {"command": command[0], "returncode": completed.returncode, "version": text[0] if text else ""}
    except Exception as exc:
        return {"command": command[0], "returncode": None, "error": f"{type(exc).__name__}: {exc}"}


def _file_record(path: Path, include_hash: bool = True) -> dict[str, Any]:
    result = {"path": str(path), "exists": path.is_file()}
    if path.is_file():
        result["size_bytes"] = path.stat().st_size
        result["sha256"] = sha256_file(path) if include_hash else None
    return result


def capture(include_model_hashes: bool = True) -> dict[str, Any]:
    settings = get_settings()
    comfy_root = Path.home() / "Documents" / "ComfyUI" / "models"
    model_paths = [
        comfy_root / "diffusion_models" / settings.comfyui_unet_model,
        comfy_root / "text_encoders" / settings.comfyui_clip_model,
        comfy_root / "vae" / settings.comfyui_vae_model,
    ]
    tracked_sources = [
        STACK_ROOT / "quality" / "datasets.json",
        STACK_ROOT / "quality" / "gates.json",
        STACK_ROOT / "scripts" / "benchmark-image-holdout.py",
        STACK_ROOT / "scripts" / "score-geneval-owlvit.py",
        STACK_ROOT / "scripts" / "compare-image-ab.py",
        STACK_ROOT / "scripts" / "select-image-route.py",
        STACK_ROOT / "scripts" / "run-image-semantic-verifier.py",
        STACK_ROOT / "scripts" / "run-image-semantic-verifier.ps1",
        STACK_ROOT / "scripts" / "smoke-image-semantic-routing.py",
        STACK_ROOT / "python-worker" / "app" / "image_precision.py",
        STACK_ROOT / "python-worker" / "app" / "openai_image_client.py",
        STACK_ROOT / "python-worker" / "app" / "settings.py",
        STACK_ROOT / "control-plane-drf" / "api" / "models.py",
        STACK_ROOT / "control-plane-drf" / "api" / "migrations" / "0003_qualityevidence.py",
        STACK_ROOT / "control-plane-drf" / "api" / "management" / "commands" / "import_quality_evidence.py",
        STACK_ROOT / "scripts" / "benchmark-cad-roundtrip.py",
        STACK_ROOT / "scripts" / "benchmark-openusd-advanced.py",
        STACK_ROOT / "quality" / "advanced-baseline.json",
        STACK_ROOT / "docker-compose.yml",
        STACK_ROOT.parent / ".github" / "workflows" / "quality-program.yml",
    ]
    lock_path = STACK_ROOT / "storage" / "quality-datasets" / "quality-datasets.lock.json"
    return {
        "schema_version": 1,
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "python": {"version": platform.python_version(), "implementation": platform.python_implementation(), "executable": sys.executable},
        "platform": {"system": platform.system(), "release": platform.release(), "machine": platform.machine()},
        "packages": {name: _version(name) for name in ("build123d", "cadpy", "usd-core", "torch", "transformers", "Pillow", "trimesh", "playwright", "pytest")},
        "native_tools": {
            "blender": _command_version([settings.blender_bin, "--version"]),
            "openscad": _command_version([settings.openscad_bin, "--version"]),
            "docker": _command_version(["docker", "version", "--format", "{{.Client.Version}}"]),
            "gpu": _command_version(["nvidia-smi", "--query-gpu=name,driver_version,memory.total", "--format=csv,noheader"]),
        },
        "models": [_file_record(path, include_model_hashes) for path in model_paths],
        "dataset_lock": _file_record(lock_path, True),
        "workflow_sources": [_file_record(path, True) for path in tracked_sources],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Capture reproducible data/model/workflow/environment versions without secrets")
    parser.add_argument("--output", type=Path, default=STACK_ROOT / "storage" / "quality-results" / "environment-lock.json")
    parser.add_argument("--skip-model-hashes", action="store_true")
    args = parser.parse_args()
    report = capture(not args.skip_model_hashes)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    missing = [item["path"] for item in report["models"] if not item["exists"]]
    print(json.dumps({"output": str(args.output.resolve()), "models": len(report["models"]), "missing_models": missing}, ensure_ascii=False))
    return 1 if missing else 0


if __name__ == "__main__":
    raise SystemExit(main())
