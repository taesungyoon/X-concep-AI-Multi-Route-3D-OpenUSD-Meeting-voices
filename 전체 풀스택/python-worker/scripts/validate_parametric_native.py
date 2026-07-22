from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Any

import numpy as np
import trimesh
from PIL import Image
from pxr import Usd

from app.blender_engine import generate_blender_asset
from app.design_state import build_design_state
from app.openscad_engine import generate_openscad
from app.openusd_exporter import export_openusd, validate_usda


CASES = [
    {
        "name": "part",
        "category": "part",
        "mode": "openscad_part",
        "prompt": (
            "폭 240mm 깊이 160mm 높이 120mm L자형 알루미늄 센서 브래킷. "
            "수직판 중앙에 센서 홀 1개, 베이스판에 체결 홀 4개, 양측 삼각 리브 2개"
        ),
        "expected_mm": [240.0, 160.0, 120.0],
    },
    {
        "name": "module",
        "category": "module",
        "mode": "openscad_module",
        "prompt": (
            "폭 800mm 깊이 600mm 높이 900mm 베이스 플레이트 위에 리니어 가이드와 "
            "서보모터 2개, 작업 지그와 센서 2개가 있는 조립 모듈"
        ),
        "expected_mm": [800.0, 600.0, 900.0],
    },
    {
        "name": "equipment",
        "category": "equipment",
        "mode": "openscad_equipment",
        "prompt": (
            "폭 1600mm 깊이 1000mm 높이 1800mm 알루미늄 프로파일 프레임 내부에 "
            "컨베이어 1대와 서보모터 2개, 컨베이어 위 비전 카메라 1개를 배치하고 "
            "전면 투명 안전도어와 우측 제어반을 포함함"
        ),
        "expected_mm": [1600.0, 1000.0, 1800.0],
    },
]


def _version(binary: str) -> str:
    completed = subprocess.run([binary, "--version"], capture_output=True, text=True, check=False)
    return (completed.stdout or completed.stderr).strip().splitlines()[0]


def _scene_extents_mm(path: Path) -> list[float]:
    loaded = trimesh.load(path, force="scene")
    bounds = np.asarray(loaded.bounds, dtype=float)
    return [round(float(value) * 1000.0, 4) for value in bounds[1] - bounds[0]]


def _image_evidence(path: Path) -> dict[str, Any]:
    with Image.open(path) as image:
        pixels = np.asarray(image.convert("RGB"), dtype=np.uint8)
        return {
            "width": image.width,
            "height": image.height,
            "non_uniform": bool(float(pixels.std()) > 2.0),
            "size_bytes": path.stat().st_size,
        }


def _coverage_passed(contract: dict[str, Any]) -> bool:
    coverage = contract.get("requirement_coverage") or {}
    rows = [*(coverage.get("components") or []), *(coverage.get("features") or []), *(coverage.get("relationships") or [])]
    return bool(rows) and all(bool(item.get("passed")) for item in rows)


def _write_summary(output_dir: Path, report: dict[str, Any]) -> None:
    report_path = output_dir / "native_validation_report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = [
        "# Native parametric CAD validation",
        "",
        f"- Overall: {'PASS' if report['passed'] else 'FAIL'}",
        f"- OpenSCAD: {report['runtime']['openscad']}",
        f"- Blender: {report['runtime']['blender']}",
        "",
        "| Mode | Native | Dimensions | Mesh | Coverage | Multi-view | OpenUSD hierarchy |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for row in report["cases"]:
        checks = row["checks"]
        mark = lambda key: "PASS" if checks[key] else "FAIL"
        lines.append(
            f"| {row['mode']} | {mark('native_provider')} | {mark('dimensions')} | "
            f"{mark('mesh')} | {mark('requirements')} | {mark('multiview_contract')} | "
            f"{mark('openusd_hierarchy')} |"
        )
    blender = report["blender"]
    lines.extend([
        "",
        f"- Blender native render: {'PASS' if blender['passed'] else 'FAIL'}",
        f"- Blender preview: `{blender.get('preview')}`",
        "",
        "This report proves deterministic contract execution and geometric checks; it does not claim a 95% benchmark score.",
    ])
    (output_dir / "NATIVE_VALIDATION_REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output_dir = args.output.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    report: dict[str, Any] = {
        "schema": "xconcep.parametric-native-validation/1.0",
        "runtime": {"openscad": _version("openscad"), "blender": _version("blender")},
        "cases": [],
    }
    equipment_source: Path | None = None
    equipment_state: dict[str, Any] | None = None

    for index, case in enumerate(CASES, start=1):
        state = build_design_state(
            project_id=f"NATIVE-{case['name'].upper()}",
            revision=1,
            prompt=case["prompt"],
            category=case["category"],
            selected_2d_id="VALIDATION-CONCEPT",
            source_analysis={"dimensions": {}},
        )
        case_dir = output_dir / case["name"]
        generated = generate_openscad(
            design_state=state,
            category=case["category"],
            output_dir=case_dir,
            openscad_bin="openscad",
            timeout_seconds=180,
            mode="native",
            generator_mode=case["mode"],
        )
        contract = json.loads(generated.geometry_json_path.read_text(encoding="utf-8"))
        manifest = json.loads(generated.manifest_path.read_text(encoding="utf-8"))
        multiview = manifest.get("multiview_validation") or {}
        multiview_views = {
            view_name: _image_evidence(case_dir / "views" / f"{view_name}.png")
            for view_name in ("front", "top", "right")
        }
        mesh = trimesh.load(generated.stl_path, force="mesh")
        stl_extents = [round(float(value), 4) for value in np.asarray(mesh.extents, dtype=float)]
        glb_extents = _scene_extents_mm(generated.glb_path)
        expected = case["expected_mm"]
        dimension_error = [round(abs(actual - target), 4) for actual, target in zip(stl_extents, expected)]

        usd = export_openusd(
            generated.glb_path,
            case_dir / "usd",
            {
                "project_id": f"NATIVE-{case['name'].upper()}",
                "category": case["category"],
                "generator_mode": case["mode"],
                "geometry_contract": contract,
            },
            generate_usdc=True,
            generate_layers=True,
        )
        stage = Usd.Stage.Open(usd["layers"]["root"])
        assembly_prims = [
            prim for prim in stage.Traverse()
            if prim.GetAttribute("xconcep:requirementId").IsValid()
        ]
        checks = {
            "native_provider": generated.provider.get("mode") == "native",
            "dimensions": max(dimension_error) <= 0.5 and max(abs(a - b) for a, b in zip(glb_extents, expected)) <= 0.5,
            "mesh": bool(mesh.is_watertight and len(mesh.vertices) > 8 and len(mesh.faces) > 12),
            "requirements": _coverage_passed(contract),
            "preview": _image_evidence(generated.preview_path)["non_uniform"],
            "multiview_contract": bool(
                multiview.get("passed")
                and multiview.get("validation_kind") == "contract_projection"
                and multiview.get("independent") is False
                and all(item["non_uniform"] for item in multiview_views.values())
            ),
            "openusd_hierarchy": len(assembly_prims) == len(contract["components"]),
            "openusd_valid": bool(validate_usda(Path(usd["usda"]))["valid"]),
        }
        report["cases"].append({
            "name": case["name"],
            "mode": case["mode"],
            "contract_sha256": contract["contract_sha256"],
            "component_count": len(contract["components"]),
            "feature_count": len(contract["features"]),
            "stl_vertices": int(len(mesh.vertices)),
            "stl_faces": int(len(mesh.faces)),
            "stl_extents_mm": stl_extents,
            "glb_extents_mm": glb_extents,
            "expected_extents_mm": expected,
            "dimension_error_mm": dimension_error,
            "preview": str(generated.preview_path),
            "multiview": {
                "passed": multiview.get("passed"),
                "score": multiview.get("score"),
                "validation_kind": multiview.get("validation_kind"),
                "independent": multiview.get("independent"),
                "report": str(case_dir / "multiview_validation.json"),
                "views": multiview_views,
            },
            "openusd_root": usd["layers"]["root"],
            "checks": checks,
            "passed": all(checks.values()),
        })
        if case["name"] == "equipment":
            equipment_source = generated.glb_path
            equipment_state = state

    assert equipment_source is not None and equipment_state is not None
    try:
        blender = generate_blender_asset(
            source_glbs=[equipment_source],
            selected_image_path=output_dir / "not-required.png",
            output_dir=output_dir / "equipment" / "blender",
            blender_bin="blender",
            timeout_seconds=300,
            mode="native",
            profile="high",
            design_state=equipment_state,
        )
        blender_image = _image_evidence(Path(blender["preview_path"]))
        report["blender"] = {
            "passed": bool(blender["provider"].get("mode") == "native" and blender_image["non_uniform"]),
            "provider": blender["provider"],
            "preview": str(blender["preview_path"]),
            "preview_evidence": blender_image,
            "glb": str(blender["glb_path"]),
            "usd": str(blender["usd_path"]) if blender.get("usd_path") else None,
            "blend": str(blender["blend_path"]) if blender.get("blend_path") else None,
        }
    except Exception as exc:
        report["blender"] = {"passed": False, "error": str(exc), "preview": None}
    report["passed"] = all(item["passed"] for item in report["cases"]) and report["blender"]["passed"]
    _write_summary(output_dir, report)
    print(json.dumps({"passed": report["passed"], "report": str(output_dir / "native_validation_report.json")}, ensure_ascii=False))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
