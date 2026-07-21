from __future__ import annotations

import argparse
import json
import math
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import trimesh
from PIL import Image

STACK_ROOT = Path(__file__).resolve().parents[1]
WORKER_ROOT = STACK_ROOT / "python-worker"
sys.path.insert(0, str(WORKER_ROOT))

from app.blender_engine import generate_blender_asset  # noqa: E402
from app.openscad_engine import generate_openscad  # noqa: E402
from app.settings import get_settings  # noqa: E402


CASES = [
    ("equipment-01", "equipment", 800, 600, 1200),
    ("equipment-02", "equipment", 900, 650, 1400),
    ("equipment-03", "equipment", 1200, 800, 1600),
    ("equipment-04", "equipment", 1600, 1000, 1800),
    ("equipment-05", "equipment", 2000, 1200, 2200),
    ("equipment-06", "equipment", 750, 500, 950),
    ("equipment-07", "equipment", 1450, 900, 1750),
    ("equipment-08", "equipment", 2400, 1400, 2100),
    ("module-01", "module", 320, 260, 280),
    ("module-02", "module", 450, 300, 520),
    ("module-03", "module", 600, 400, 700),
    ("module-04", "module", 800, 600, 900),
    ("module-05", "module", 1000, 700, 1100),
    ("module-06", "module", 1250, 800, 950),
    ("part-01", "part", 80, 50, 40),
    ("part-02", "part", 120, 80, 60),
    ("part-03", "part", 180, 120, 90),
    ("part-04", "part", 240, 160, 120),
    ("part-05", "part", 360, 220, 180),
    ("part-06", "part", 500, 300, 240),
]
BLENDER_CASE_INDEXES = [0, 5, 10, 15, 19]


def _scene_metrics(path: Path) -> dict[str, Any]:
    loaded = trimesh.load(path, force="scene")
    if isinstance(loaded, trimesh.Trimesh):
        loaded = trimesh.Scene(loaded)
    meshes: list[trimesh.Trimesh] = []
    materials = 0
    for node in loaded.graph.nodes_geometry:
        transform, geom_name = loaded.graph.get(node)
        mesh = loaded.geometry[geom_name].copy()
        mesh.apply_transform(transform)
        if isinstance(mesh, trimesh.Trimesh):
            meshes.append(mesh)
            if getattr(mesh.visual, "material", None) is not None:
                materials += 1
    if not meshes:
        raise RuntimeError(f"No mesh in {path}")
    merged = trimesh.util.concatenate(meshes)
    return {
        "mesh_count": len(meshes),
        "vertex_count": int(sum(len(mesh.vertices) for mesh in meshes)),
        "face_count": int(sum(len(mesh.faces) for mesh in meshes)),
        "watertight_meshes": int(sum(bool(mesh.is_watertight) for mesh in meshes)),
        "extents_m": [float(value) for value in merged.bounding_box.extents],
        "finite": bool(np.isfinite(merged.vertices).all()),
        "volume_m3": float(abs(merged.volume)),
        "material_count": materials,
    }


def _errors(actual: list[float], expected: list[float]) -> list[float]:
    return [abs(a - e) / max(e, 1e-12) * 100 for a, e in zip(actual, expected)]


def _artifact_ok(path: Path | None, minimum_bytes: int = 1) -> bool:
    return bool(path and path.is_file() and path.stat().st_size >= minimum_bytes)


def _design_state(case_id: str, width: float, depth: float, height: float) -> dict[str, Any]:
    return {
        "design_id": case_id,
        "revision": 1,
        "purpose": "산업용 자동화 구조 정확도 벤치마크",
        "source_prompt": f"폭 {width}mm 깊이 {depth}mm 높이 {height}mm 구조",
        "dimensions": {"width_mm": width, "depth_mm": depth, "height_mm": height},
        "components": [
            {"id": "frame", "name": "프레임", "required": True},
            {"id": "work_unit", "name": "작업 유닛", "required": True},
        ],
        "coordinate_system": {"up_axis": "Z", "units": "m"},
        "visual": {"style": "industrial hard-surface", "material": "painted steel"},
    }


def _structural_case(case: tuple[str, str, float, float, float], root: Path, openscad_bin: str) -> dict[str, Any]:
    case_id, category, width, depth, height = case
    state = _design_state(case_id, width, depth, height)
    started = time.perf_counter()
    generated = generate_openscad(
        design_state=state,
        category=category,
        output_dir=root / case_id / "structural",
        openscad_bin=openscad_bin,
        timeout_seconds=180,
        mode="native",
    )
    metrics = _scene_metrics(generated.glb_path)
    expected = [width / 1000, depth / 1000, height / 1000]
    errors = _errors(metrics["extents_m"], expected)
    files = {
        "scad": _artifact_ok(generated.scad_path, 100),
        "stl": _artifact_ok(generated.stl_path, 200),
        "glb": _artifact_ok(generated.glb_path, 200),
        "preview": _artifact_ok(generated.preview_path, 1000),
        "manifest": _artifact_ok(generated.manifest_path, 100),
        "geometry_json": _artifact_ok(generated.geometry_json_path, 100),
    }
    checks = {
        "native_provider": generated.provider.get("mode") == "native",
        "dimensions_within_1pct": all(value <= 1.0 for value in errors),
        "finite_geometry": metrics["finite"],
        "faces_present": metrics["face_count"] > 0,
        "watertight": metrics["watertight_meshes"] == metrics["mesh_count"],
        "positive_volume": math.isfinite(metrics["volume_m3"]) and metrics["volume_m3"] > 0,
        "artifacts": all(files.values()),
    }
    return {
        "id": case_id,
        "kind": "openscad",
        "category": category,
        "passed": all(checks.values()),
        "duration_seconds": round(time.perf_counter() - started, 3),
        "expected_m": expected,
        "dimension_error_pct": [round(value, 4) for value in errors],
        "checks": checks,
        "files": files,
        "metrics": metrics,
        "provider": generated.provider,
        "state": state,
        "source_glb": str(generated.glb_path),
    }


def _blender_case(source: dict[str, Any], index: int, root: Path, blender_bin: str, reference: Path) -> dict[str, Any]:
    case_id = f"blender-{index + 1:02d}-{source['id']}"
    output = root / case_id / "high_quality"
    started = time.perf_counter()
    generated = generate_blender_asset(
        source_glbs=[Path(source["source_glb"])],
        selected_image_path=reference,
        output_dir=output,
        blender_bin=blender_bin,
        timeout_seconds=300,
        mode="native",
        profile="final" if index == len(BLENDER_CASE_INDEXES) - 1 else "standard",
        design_state=source["state"],
    )
    metrics = _scene_metrics(generated["glb_path"])
    source_extents = source["metrics"]["extents_m"]
    errors = _errors(metrics["extents_m"], source_extents)
    png_ok = False
    png_size = None
    if _artifact_ok(generated["preview_path"], 10_000):
        with Image.open(generated["preview_path"]) as image:
            png_size = list(image.size)
            png_ok = image.width >= 1280 and image.height >= 860
    files = {
        "glb": _artifact_ok(generated["glb_path"], 500),
        "png": png_ok,
        "blend": _artifact_ok(generated["blend_path"], 1000),
        "script": _artifact_ok(generated["script_path"], 500),
        "materials": _artifact_ok(generated["materials_path"], 100),
    }
    checks = {
        "native_provider": generated["provider"].get("mode") == "native",
        "source_dimensions_preserved_1_5pct": all(value <= 1.5 for value in errors),
        "ground_not_exported": max(metrics["extents_m"]) <= max(source_extents) * 1.02,
        "finite_geometry": metrics["finite"],
        "faces_present": metrics["face_count"] > 0,
        "pbr_material_present": metrics["material_count"] >= 1,
        "artifacts": all(files.values()),
    }
    return {
        "id": case_id,
        "kind": "blender",
        "source": source["id"],
        "passed": all(checks.values()),
        "duration_seconds": round(time.perf_counter() - started, 3),
        "dimension_error_pct": [round(value, 4) for value in errors],
        "checks": checks,
        "files": files,
        "render_size": png_size,
        "metrics": metrics,
        "provider": generated["provider"],
    }


def _markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Native CAD Acceptance Benchmark",
        "",
        f"- Result: **{report['passed_cases']}/{report['total_cases']} ({report['acceptance_rate_pct']:.2f}%)**",
        f"- Target: {report['target_rate_pct']:.2f}%",
        f"- OpenSCAD: `{report['openscad_bin']}`",
        f"- Blender: `{report['blender_bin']}`",
        "",
        "| Case | Engine | Result | Time (s) | Max dimension error |",
        "|---|---|---:|---:|---:|",
    ]
    for case in report["cases"]:
        max_error = max(case.get("dimension_error_pct") or [0])
        lines.append(f"| {case['id']} | {case['kind']} | {'PASS' if case['passed'] else 'FAIL'} | {case['duration_seconds']:.3f} | {max_error:.4f}% |")
    lines.extend(["", "95%는 위 자동 acceptance 계약 기준이며 제조 승인 정확도를 의미하지 않음.", ""])
    return "\n".join(lines)


def main() -> int:
    settings = get_settings()
    parser = argparse.ArgumentParser(description="Native OpenSCAD/Blender acceptance benchmark")
    parser.add_argument("--openscad-bin", default=settings.openscad_bin)
    parser.add_argument("--blender-bin", default=settings.blender_bin)
    parser.add_argument("--output", type=Path, default=STACK_ROOT / "storage" / "benchmarks" / "native-cad")
    parser.add_argument("--target", type=float, default=95.0)
    args = parser.parse_args()

    run_id = datetime.now().strftime("%Y%m%d-%H%M%S")
    run_root = args.output.resolve() / run_id
    run_root.mkdir(parents=True, exist_ok=False)
    reference = run_root / "reference.png"
    Image.new("RGB", (64, 64), (42, 66, 82)).save(reference)

    cases: list[dict[str, Any]] = []
    for case in CASES:
        try:
            result = _structural_case(case, run_root, args.openscad_bin)
        except Exception as exc:
            result = {"id": case[0], "kind": "openscad", "passed": False, "error": repr(exc), "duration_seconds": 0.0}
        cases.append(result)
        print(f"[{len(cases):02d}/25] {result['id']}: {'PASS' if result['passed'] else 'FAIL'}", flush=True)

    structural = list(cases)
    for blender_index, source_index in enumerate(BLENDER_CASE_INDEXES):
        source = structural[source_index]
        if not source.get("passed"):
            result = {
                "id": f"blender-{blender_index + 1:02d}-{source['id']}", "kind": "blender", "passed": False,
                "error": "source structural case failed", "duration_seconds": 0.0,
            }
        else:
            try:
                result = _blender_case(source, blender_index, run_root, args.blender_bin, reference)
            except Exception as exc:
                result = {
                    "id": f"blender-{blender_index + 1:02d}-{source['id']}", "kind": "blender", "passed": False,
                    "error": repr(exc), "duration_seconds": 0.0,
                }
        cases.append(result)
        print(f"[{len(cases):02d}/25] {result['id']}: {'PASS' if result['passed'] else 'FAIL'}", flush=True)

    passed = sum(bool(case["passed"]) for case in cases)
    rate = passed / len(cases) * 100
    report = {
        "benchmark_version": "1.0",
        "run_id": run_id,
        "target_rate_pct": args.target,
        "total_cases": len(cases),
        "passed_cases": passed,
        "acceptance_rate_pct": round(rate, 4),
        "passed": rate >= args.target,
        "openscad_bin": str(Path(args.openscad_bin).resolve()),
        "blender_bin": str(Path(args.blender_bin).resolve()),
        "cases": cases,
    }
    (run_root / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    (run_root / "report.md").write_text(_markdown(report), encoding="utf-8")
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "latest.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    (args.output / "latest.md").write_text(_markdown(report), encoding="utf-8")
    print(json.dumps({key: report[key] for key in ("passed", "passed_cases", "total_cases", "acceptance_rate_pct")}, ensure_ascii=False))
    print(f"Report: {run_root / 'report.md'}")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
