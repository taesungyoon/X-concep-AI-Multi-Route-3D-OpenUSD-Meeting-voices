from __future__ import annotations

import argparse
from pathlib import Path

import trimesh
from PIL import Image

from main import engine


def main() -> None:
    service_dir = Path(__file__).resolve().parent
    repository_root = next(
        (parent for parent in service_dir.parents if (parent / ".git").exists()),
        service_dir.parent,
    )
    default_input = repository_root / "전체 풀스택" / "storage" / "comfyui-live-test.png"
    if not default_input.is_file():
        default_input = service_dir.parent / "storage" / "comfyui-live-test.png"
    parser = argparse.ArgumentParser(description="Run a real TripoSR GPU smoke test")
    parser.add_argument(
        "--input",
        type=Path,
        default=default_input,
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=repository_root / ".triposr-runtime" / "comfyui-live-test.glb",
    )
    parser.add_argument("--resolution", type=int, default=128)
    parser.add_argument("--remove-background", action="store_true")
    args = parser.parse_args()

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(args.input) as opened:
        payload = engine.generate(
            opened.convert("RGBA"),
            remove_bg=args.remove_background,
            ratio=0.85,
            resolution=args.resolution,
        )
    args.output.write_bytes(payload)
    scene = trimesh.load(args.output, force="scene")
    geometry_count = len(scene.geometry)
    if geometry_count < 1:
        raise RuntimeError("Generated GLB contains no geometry")
    print(
        {
            "output": str(args.output.resolve()),
            "bytes": len(payload),
            "geometry_count": geometry_count,
            "loaded": engine.loaded,
            "device": engine.device,
        }
    )


if __name__ == "__main__":
    main()
