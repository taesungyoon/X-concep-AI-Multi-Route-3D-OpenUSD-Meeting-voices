from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
STACK_ROOT = PACKAGE_ROOT.parents[1]
WORKER_ROOT = STACK_ROOT / "python-worker"
sys.path.insert(0, str(WORKER_ROOT))
sys.path.insert(0, str(PACKAGE_ROOT / "src"))

from app.design_state import build_design_state
from app.parametric_generators import MODE_FOR_CATEGORY, build_geometry_contract
from xconcep_cad_vlm.dataset import validate_dataset
from xconcep_cad_vlm.php_cad import import_php_cad_packages
from xconcep_cad_vlm.preprocess import preprocess_dataset


SAMPLES = [
    {
        "id": "part_l_bracket_001", "category": "part", "split": "train",
        "prompt": "폭 240mm, 깊이 160mm, 높이 120mm 알루미늄 L형 센서 브래킷. 체결 홀 4개, 센서 홀 1개, 삼각 리브 2개.",
        "dimensions": {"width": 240, "depth": 160, "height": 120},
    },
    {
        "id": "part_sensor_mount_002", "category": "part", "split": "train",
        "prompt": "폭 200mm, 깊이 140mm, 높이 90mm 비전 카메라용 브래킷. 체결 홀 4개와 센서 홀 2개, 리브 1개.",
        "dimensions": {"width": 200, "depth": 140, "height": 90},
    },
    {
        "id": "part_motor_mount_003", "category": "part", "split": "eval",
        "prompt": "폭 280mm, 깊이 190mm, 높이 150mm 서보모터용 강판 브래킷. 체결 홀 6개, 센서 홀 1개, 삼각 리브 3개.",
        "dimensions": {"width": 280, "depth": 190, "height": 150},
    },
    {
        "id": "module_linear_jig_001", "category": "module", "split": "train",
        "prompt": "폭 800mm, 깊이 600mm, 높이 900mm 작업 모듈. 리니어 가이드 2개, 서보모터 1개, 작업 지그와 센서 1개 포함.",
        "dimensions": {"width": 800, "depth": 600, "height": 900},
    },
    {
        "id": "module_vision_jig_002", "category": "module", "split": "train",
        "prompt": "폭 700mm, 깊이 520mm, 높이 780mm 검사 지그 모듈. 리니어 가이드 2개, 서보모터 2개, 비전 카메라 1개와 작업 지그 포함.",
        "dimensions": {"width": 700, "depth": 520, "height": 780},
    },
    {
        "id": "module_dual_servo_003", "category": "module", "split": "eval",
        "prompt": "폭 950mm, 깊이 680mm, 높이 1000mm 이송 모듈. 리니어 가이드 2개와 서보모터 2개, 센서 2개, 작업 지그 포함.",
        "dimensions": {"width": 950, "depth": 680, "height": 1000},
    },
    {
        "id": "equipment_conveyor_inspection_001", "category": "equipment", "split": "train",
        "prompt": "폭 1600mm, 깊이 1000mm, 높이 1800mm 알루미늄 프로파일 검사 설비. 컨베이어 1개, 서보모터 2개, 컨베이어 위 비전 카메라 1개, 전면 안전도어와 우측 제어반.",
        "dimensions": {"width": 1600, "depth": 1000, "height": 1800},
    },
    {
        "id": "equipment_safety_cell_002", "category": "equipment", "split": "train",
        "prompt": "폭 1400mm, 깊이 900mm, 높이 1700mm 조립 설비. 컨베이어 1개, 서보모터 1개, 안전커버와 전면 안전도어, 우측 제어반 포함.",
        "dimensions": {"width": 1400, "depth": 900, "height": 1700},
    },
    {
        "id": "equipment_camera_cell_003", "category": "equipment", "split": "eval",
        "prompt": "폭 1800mm, 깊이 1200mm, 높이 2100mm 비전 검사 설비. 컨베이어 1개 위에 비전 카메라 1개, 서보모터 3개, 전면 안전도어와 우측 제어반.",
        "dimensions": {"width": 1800, "depth": 1200, "height": 2100},
    },
]

COLORS = {
    "brushed_aluminum": (180, 188, 194), "painted_steel": (100, 118, 132),
    "hardened_steel": (85, 92, 100), "industrial_black": (45, 50, 56),
    "industrial_blue": (48, 105, 166), "sensor_black": (28, 33, 38),
    "aluminum_profile": (168, 174, 180), "conveyor_steel": (95, 110, 120),
    "conveyor_roller": (75, 83, 90), "transparent_polycarbonate": (130, 205, 220),
    "control_gray": (110, 120, 128), "glass": (70, 140, 190),
}
VIEWS = {"front": (0, 2), "top": (0, 1), "right": (1, 2)}


def _extents(component: dict[str, Any]) -> list[float]:
    if component.get("shape") == "box":
        return [float(value) for value in component["size_mm"]]
    diameter = float(component.get("diameter_mm", 1))
    height = float(component.get("height_mm", 1))
    axis = str(component.get("axis", "Z")).upper()
    result = [diameter, diameter, diameter]
    result[{"X": 0, "Y": 1, "Z": 2}.get(axis, 2)] = height
    return result


def _project(value: float, origin: float, span: float, start: float, pixels: float, invert: bool = False) -> float:
    normalized = (value - origin) / max(span, 1e-6)
    if invert:
        normalized = 1.0 - normalized
    return start + normalized * pixels


def render_view(contract: dict[str, Any], view_name: str, output: Path) -> None:
    image = Image.new("RGB", (640, 480), (246, 248, 250))
    draw = ImageDraw.Draw(image, "RGBA")
    draw.rectangle((35, 35, 605, 445), fill=(255, 255, 255, 255), outline=(90, 105, 120, 255), width=2)
    axes = VIEWS[view_name]
    overall = contract["overall"]
    spans = [float(overall["width"]), float(overall["depth"]), float(overall["height"])]
    origins = [-spans[0] / 2, -spans[1] / 2, 0.0]
    usable_w, usable_h = 500.0, 340.0
    scale = min(usable_w / spans[axes[0]], usable_h / spans[axes[1]])
    plot_w, plot_h = spans[axes[0]] * scale, spans[axes[1]] * scale
    left, top = (640 - plot_w) / 2, (480 - plot_h) / 2 + 10
    draw.rectangle((left, top, left + plot_w, top + plot_h), outline=(130, 145, 158, 180), width=1)
    depth_axis = ({0, 1, 2} - set(axes)).pop()
    components = sorted(contract.get("components", []), key=lambda item: float(item.get("center_mm", [0, 0, 0])[depth_axis]))
    for component in components:
        center = [float(value) for value in component.get("center_mm", [0, 0, 0])]
        size = _extents(component)
        u0 = _project(center[axes[0]] - size[axes[0]] / 2, origins[axes[0]], spans[axes[0]], left, plot_w)
        u1 = _project(center[axes[0]] + size[axes[0]] / 2, origins[axes[0]], spans[axes[0]], left, plot_w)
        v0 = _project(center[axes[1]] + size[axes[1]] / 2, origins[axes[1]], spans[axes[1]], top, plot_h, True)
        v1 = _project(center[axes[1]] - size[axes[1]] / 2, origins[axes[1]], spans[axes[1]], top, plot_h, True)
        color = COLORS.get(str(component.get("material_preset")), (120, 135, 145))
        alpha = 90 if component.get("material_preset") == "transparent_polycarbonate" else 205
        shape = (u0, v0, u1, v1)
        if component.get("shape") == "cylinder" and str(component.get("axis", "Z")).upper() != ("X", "Y", "Z")[depth_axis]:
            draw.ellipse(shape, fill=(*color, alpha), outline=(35, 45, 55, 255), width=1)
        else:
            draw.rectangle(shape, fill=(*color, alpha), outline=(35, 45, 55, 255), width=1)
    for feature in contract.get("features", []):
        axis = {"X": 0, "Y": 1, "Z": 2}.get(str(feature.get("axis", "Z")).upper(), 2)
        if axis != depth_axis:
            continue
        center = [float(value) for value in feature.get("center_mm", [0, 0, 0])]
        radius = max(2.0, float(feature.get("diameter_mm", 4)) * scale / 2)
        u = _project(center[axes[0]], origins[axes[0]], spans[axes[0]], left, plot_w)
        v = _project(center[axes[1]], origins[axes[1]], spans[axes[1]], top, plot_h, True)
        draw.ellipse((u - radius, v - radius, u + radius, v + radius), fill=(250, 250, 250, 255), outline=(180, 40, 40, 255), width=2)
    draw.text((45, 45), f"{view_name.upper()} VIEW", fill=(25, 35, 45, 255))
    draw.text((45, 420), f"{overall['width']:.0f} x {overall['depth']:.0f} x {overall['height']:.0f} mm", fill=(35, 45, 55, 255))
    image.save(output, format="PNG", optimize=True)


def _php_geometry(sample_id: str, contract: dict[str, Any]) -> dict[str, Any]:
    overall = contract["overall"]
    width, depth, height = (float(overall[key]) for key in ("width", "depth", "height"))
    components = contract.get("components", [])
    return {
        "schema_version": "1.0", "sample_id": sample_id, "parser_mode": "xconcep_parametric_to_php_package_v1",
        "entity_counts": {"COMPONENT": len(components), "FEATURE": len(contract.get("features", []))},
        "points": [item.get("center_mm", [0, 0, 0]) for item in components], "primitives": [],
        "bbox": {"min": [-width / 2, -depth / 2, 0.0], "max": [width / 2, depth / 2, height], "extent": [width, depth, height]},
        "topology": {}, "surfaces": {}, "normalization": {"units": "mm"},
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build examples through the PHP CAD package import pipeline")
    parser.add_argument("--output", default=str(PACKAGE_ROOT / "data" / "examples"))
    parser.add_argument("--replace", action="store_true", help="replace an existing generated output directory")
    args = parser.parse_args()
    output = Path(args.output).expanduser().resolve()
    if output.exists() and not args.replace:
        parser.error(f"output already exists: {output}; pass --replace to regenerate")
    workspace = output.with_name(output.name + ".php-build")
    if workspace.exists():
        shutil.rmtree(workspace)
    packages = workspace / "php-packages"
    for sample in SAMPLES:
        state = build_design_state(
            project_id=f"TRAIN-{sample['id'].upper()}", revision=1, prompt=sample["prompt"],
            category=sample["category"], selected_2d_id=f"SYNTH-{sample['id']}",
            source_analysis={"dimensions": sample["dimensions"]},
        )
        contract = build_geometry_contract(state, sample["category"], MODE_FOR_CATEGORY[sample["category"]])
        sample_id = f"CAD-{sample['id'].upper()}"
        package = packages / sample_id
        (package / "geometry").mkdir(parents=True)
        (package / "quality").mkdir()
        (package / "metadata").mkdir()
        geometry = _php_geometry(sample_id, contract)
        source_sha = hashlib.sha256(json.dumps(geometry, sort_keys=True).encode()).hexdigest()
        (package / "geometry" / "geometry.json").write_text(json.dumps(geometry, ensure_ascii=False), encoding="utf-8")
        (package / "quality" / "report.json").write_text(json.dumps({"score": 1.0}), encoding="utf-8")
        (package / "metadata" / "label.json").write_text(json.dumps({"category": sample["category"], "description": sample["prompt"], "training_prompt": sample["prompt"]}, ensure_ascii=False), encoding="utf-8")
        (package / "manifest.json").write_text(json.dumps({"schema_version": "1.0", "sample_id": sample_id, "source": {"format": "xconcep_parametric", "sha256": source_sha}, "label": {"category": sample["category"]}, "split": sample["split"], "provenance": {"pipeline": "xconcep-php-compatible", "version": contract["generator_version"]}}, ensure_ascii=False), encoding="utf-8")
    raw = workspace / "raw"
    import_php_cad_packages(packages, raw, license_id="LicenseRef-Xconcep-Internal-Generated", training_allowed=True, minimum_quality=0.9)
    prepared = workspace / "prepared"
    preprocess_dataset(raw / "records.jsonl", prepared, min_images=1)
    if output.exists():
        shutil.rmtree(output)
    prepared.replace(output)
    records = [json.loads(line) for line in (output / "records.jsonl").read_text(encoding="utf-8").splitlines() if line]
    (output / "gold_eval_predictions.example.jsonl").write_text(
        "".join(
            json.dumps({"id": record["id"], "prediction": record["design_spec"]}, ensure_ascii=False, sort_keys=True) + "\n"
            for record in records if record["split"] == "eval"
        ),
        encoding="utf-8",
    )
    shutil.copyfile(PACKAGE_ROOT / "schema" / "license_allowlist.json", output / "license_allowlist.json")
    summary = {
        "schema": "xconcep.cad-vlm-manifest/1.0", "record_count": len(records),
        "categories": dict(Counter(item["category"] for item in records)),
        "splits": dict(Counter(item["split"] for item in records)),
        "views_per_record": ["php_observed"], "target_default": "design_spec",
        "gold_evaluation_example": "gold_eval_predictions.example.jsonl",
        "note": "Examples verify the pipeline only; they are not sufficient for production training.",
    }
    (output / "manifest.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(validate_dataset(output), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
