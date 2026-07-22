from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont


VIEW_AXES = {
    "front": (0, 2, "X", "Z"),
    "top": (0, 1, "X", "Y"),
    "right": (1, 2, "Y", "Z"),
}
AXIS_INDEX = {"X": 0, "Y": 1, "Z": 2}


def _font(size: int, bold: bool = False) -> ImageFont.ImageFont:
    names = [
        "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf" if bold else "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc" if bold else "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
        "C:/Windows/Fonts/malgunbd.ttf" if bold else "C:/Windows/Fonts/malgun.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for name in names:
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _component_bounds(item: dict[str, Any]) -> tuple[list[float], list[float]] | None:
    center = item.get("center_mm")
    if not isinstance(center, list) or len(center) != 3:
        return None
    if item.get("shape") == "cylinder":
        diameter = float(item.get("diameter_mm") or 0.0)
        height = float(item.get("height_mm") or 0.0)
        extents = [diameter, diameter, diameter]
        extents[AXIS_INDEX.get(str(item.get("axis") or "Z").upper(), 2)] = height
    else:
        size = item.get("size_mm")
        if not isinstance(size, list) or len(size) != 3:
            return None
        extents = [float(value) for value in size]
    if any(value <= 0 for value in extents):
        return None
    center_values = [float(value) for value in center]
    return (
        [center_values[index] - extents[index] / 2 for index in range(3)],
        [center_values[index] + extents[index] / 2 for index in range(3)],
    )


def _union_bounds(bounds: list[tuple[list[float], list[float]]]) -> tuple[list[float], list[float]] | None:
    if not bounds:
        return None
    return (
        [min(item[0][axis] for item in bounds) for axis in range(3)],
        [max(item[1][axis] for item in bounds) for axis in range(3)],
    )


def _requirement_id(item: dict[str, Any]) -> str:
    return str(item.get("requirement_id") or item.get("kind") or item.get("id") or "component")


def _group_bounds(contract: dict[str, Any]) -> dict[str, tuple[list[float], list[float]]]:
    grouped: dict[str, list[tuple[list[float], list[float]]]] = {}
    for item in contract.get("components") or []:
        bounds = _component_bounds(item)
        if bounds:
            grouped.setdefault(_requirement_id(item), []).append(bounds)
    return {
        requirement_id: union
        for requirement_id, values in grouped.items()
        if (union := _union_bounds(values)) is not None
    }


def _target_ranges(contract: dict[str, Any]) -> list[tuple[float, float]]:
    overall = contract.get("overall") or {}
    width = float(overall.get("width") or 1.0)
    depth = float(overall.get("depth") or 1.0)
    height = float(overall.get("height") or 1.0)
    return [(-width / 2, width / 2), (-depth / 2, depth / 2), (0.0, height)]


def _color(requirement_id: str) -> tuple[int, int, int, int]:
    raw = hashlib.sha256(requirement_id.encode("utf-8")).digest()
    return (65 + raw[0] % 130, 80 + raw[1] % 130, 95 + raw[2] % 130, 105)


def _draw_dashed_rectangle(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], fill: str) -> None:
    left, top, right, bottom = box
    step = 14
    for start in range(left, right, step * 2):
        draw.line((start, top, min(start + step, right), top), fill=fill, width=2)
        draw.line((start, bottom, min(start + step, right), bottom), fill=fill, width=2)
    for start in range(top, bottom, step * 2):
        draw.line((left, start, left, min(start + step, bottom)), fill=fill, width=2)
        draw.line((right, start, right, min(start + step, bottom)), fill=fill, width=2)


def _render_view(
    contract: dict[str, Any],
    output_path: Path,
    view_name: str,
    group_bounds: dict[str, tuple[list[float], list[float]]],
) -> dict[str, Any]:
    horizontal_axis, vertical_axis, horizontal_label, vertical_label = VIEW_AXES[view_name]
    ranges = _target_ranges(contract)
    h_min, h_max = ranges[horizontal_axis]
    v_min, v_max = ranges[vertical_axis]
    h_pad = max((h_max - h_min) * 0.07, 1.0)
    v_pad = max((v_max - v_min) * 0.07, 1.0)
    h_min, h_max = h_min - h_pad, h_max + h_pad
    v_min, v_max = v_min - v_pad, v_max + v_pad

    image = Image.new("RGB", (960, 720), (5, 16, 28))
    draw = ImageDraw.Draw(image, "RGBA")
    plot = (70, 105, 900, 650)

    def project(horizontal: float, vertical: float) -> tuple[int, int]:
        x = plot[0] + int((horizontal - h_min) / max(h_max - h_min, 1e-9) * (plot[2] - plot[0]))
        y = plot[3] - int((vertical - v_min) / max(v_max - v_min, 1e-9) * (plot[3] - plot[1]))
        return x, y

    draw.text((36, 28), f"{view_name.upper()} CONTRACT VIEW", font=_font(26, True), fill="#dff9ff")
    draw.text((36, 66), f"{horizontal_label} / {vertical_label} orthographic projection · units mm", font=_font(14), fill="#7899ad")
    target_a = project(ranges[horizontal_axis][0], ranges[vertical_axis][0])
    target_b = project(ranges[horizontal_axis][1], ranges[vertical_axis][1])
    envelope_box = (
        min(target_a[0], target_b[0]),
        min(target_a[1], target_b[1]),
        max(target_a[0], target_b[0]),
        max(target_a[1], target_b[1]),
    )
    _draw_dashed_rectangle(draw, envelope_box, "#42d7ee")

    visible_requirements: set[str] = set()
    labelled: set[str] = set()
    for item in contract.get("components") or []:
        bounds = _component_bounds(item)
        if not bounds:
            continue
        requirement_id = _requirement_id(item)
        point_a = project(bounds[0][horizontal_axis], bounds[0][vertical_axis])
        point_b = project(bounds[1][horizontal_axis], bounds[1][vertical_axis])
        box = (
            min(point_a[0], point_b[0]),
            min(point_a[1], point_b[1]),
            max(point_a[0], point_b[0]),
            max(point_a[1], point_b[1]),
        )
        projected_width = max(0, box[2] - box[0])
        projected_height = max(0, box[3] - box[1])
        if projected_width >= 1 and projected_height >= 1:
            visible_requirements.add(requirement_id)
        color = _color(requirement_id)
        material = str(item.get("material_preset") or "")
        if requirement_id == "safety_door" or "transparent" in material or material == "glass":
            fill_color = (color[0], color[1], color[2], 28)
        elif requirement_id == "frame":
            fill_color = (color[0], color[1], color[2], 42)
        else:
            fill_color = (color[0], color[1], color[2], 145)
        draw.rectangle(box, fill=fill_color, outline=(color[0], color[1], color[2], 235), width=2)
        if requirement_id not in labelled and projected_width > 18 and projected_height > 12:
            draw.text((box[0] + 4, box[1] + 3), requirement_id[:24], font=_font(10), fill="#f2fbff")
            labelled.add(requirement_id)

    draw.text((700, 66), f"Visible requirements: {len(visible_requirements)}", font=_font(12, True), fill="#75dfa0")
    for index, requirement_id in enumerate(sorted(group_bounds)):
        column = index % 3
        row = index // 3
        x = 70 + column * 285
        y = 664 + row * 22
        color = _color(requirement_id)
        draw.rectangle((x, y, x + 12, y + 12), fill=(color[0], color[1], color[2], 220))
        draw.text((x + 18, y - 2), requirement_id[:28], font=_font(10), fill="#a9c2d0")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(output_path, "PNG")
    return {
        "file": output_path.name,
        "axes": [horizontal_label, vertical_label],
        "visible_requirements": sorted(visible_requirements),
        "projected_group_count": len(group_bounds),
    }


def _relationship_result(
    relationship: dict[str, Any],
    groups: dict[str, tuple[list[float], list[float]]],
) -> dict[str, Any]:
    subject = str(relationship.get("subject") or "")
    object_id = str(relationship.get("object") or "")
    relation = str(relationship.get("relation") or "")
    subject_bounds = groups.get(subject)
    object_bounds = groups.get(object_id)
    if not subject_bounds or not object_bounds:
        return {**relationship, "passed": False, "reason": "required component group missing"}

    subject_center = [(subject_bounds[0][axis] + subject_bounds[1][axis]) / 2 for axis in range(3)]
    object_center = [(object_bounds[0][axis] + object_bounds[1][axis]) / 2 for axis in range(3)]
    if relation == "above":
        passed = subject_bounds[0][2] >= object_bounds[1][2]
    elif relation == "below":
        passed = subject_bounds[1][2] <= object_bounds[0][2]
    elif relation == "right_of":
        passed = subject_center[0] > object_center[0]
    elif relation == "left_of":
        passed = subject_center[0] < object_center[0]
    elif relation == "front_of":
        passed = subject_center[1] < object_center[1]
    elif relation == "behind":
        passed = subject_center[1] > object_center[1]
    else:
        passed = False
    return {
        **relationship,
        "passed": passed,
        "subject_center_mm": [round(value, 3) for value in subject_center],
        "object_center_mm": [round(value, 3) for value in object_center],
    }


def validate_contract_multiview(
    contract: dict[str, Any],
    output_dir: Path,
    *,
    envelope_tolerance_pct: float = 1.0,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    groups = _group_bounds(contract)
    component_bounds = [
        bounds
        for item in contract.get("components") or []
        if (bounds := _component_bounds(item)) is not None
    ]
    actual = _union_bounds(component_bounds)
    target_ranges = _target_ranges(contract)
    expected_extents = [high - low for low, high in target_ranges]
    actual_extents = [
        actual[1][axis] - actual[0][axis] if actual else 0.0
        for axis in range(3)
    ]
    error_pct = [
        abs(actual_extents[axis] - expected_extents[axis]) / max(expected_extents[axis], 1e-9) * 100
        for axis in range(3)
    ]
    envelope_passed = actual is not None and all(error <= envelope_tolerance_pct for error in error_pct)

    views: dict[str, dict[str, Any]] = {}
    for view_name in VIEW_AXES:
        view_path = output_dir / f"{view_name}.png"
        views[view_name] = _render_view(contract, view_path, view_name, groups)
        views[view_name]["file"] = f"views/{view_path.name}"

    coverage = contract.get("requirement_coverage") or {}
    required_ids = [
        str(item.get("id"))
        for item in coverage.get("components") or []
        if int(item.get("required") or 0) > 0
    ]
    visibility_rows = []
    for requirement_id in required_ids:
        visible_in = [
            view_name
            for view_name, view in views.items()
            if requirement_id in view["visible_requirements"]
        ]
        visibility_rows.append({
            "id": requirement_id,
            "visible_in": visible_in,
            "required_view_count": 2,
            "passed": len(visible_in) >= 2,
        })
    visibility_passed = bool(visibility_rows) and all(item["passed"] for item in visibility_rows)

    relationship_rows = [
        _relationship_result(item, groups)
        for item in contract.get("relationships") or []
        if item.get("required", True)
    ]
    relationships_passed = all(item["passed"] for item in relationship_rows)

    failed_scopes = {
        item["id"] for item in visibility_rows if not item["passed"]
    }
    failed_scopes.update(
        str(item.get("subject"))
        for item in relationship_rows
        if not item.get("passed") and item.get("subject")
    )
    if not envelope_passed:
        failed_scopes.update(required_ids)

    envelope_score = max(0.0, 1.0 - sum(min(error, 100.0) for error in error_pct) / 300.0)
    visibility_score = (
        sum(item["passed"] for item in visibility_rows) / len(visibility_rows)
        if visibility_rows else 0.0
    )
    relationship_score = (
        sum(item["passed"] for item in relationship_rows) / len(relationship_rows)
        if relationship_rows else 1.0
    )
    passed = envelope_passed and visibility_passed and relationships_passed
    report = {
        "schema": "xconcep.contract-multiview/1.0",
        "validation_kind": "contract_projection",
        "independent": False,
        "passed": passed,
        "score": round(envelope_score * 0.35 + visibility_score * 0.35 + relationship_score * 0.30, 3),
        "checks": [
            {
                "id": "orthographic_envelope",
                "label": "정면·상면·측면 외곽 치수",
                "passed": envelope_passed,
                "value": {
                    "expected_mm": [round(value, 3) for value in expected_extents],
                    "actual_mm": [round(value, 3) for value in actual_extents],
                    "error_pct": [round(value, 3) for value in error_pct],
                    "tolerance_pct": envelope_tolerance_pct,
                },
            },
            {
                "id": "required_visibility",
                "label": "필수 구성요소 다중 시점 가시성",
                "passed": visibility_passed,
                "value": visibility_rows,
            },
            {
                "id": "geometric_relationships",
                "label": "배치 관계 좌표 검증",
                "passed": relationships_passed,
                "value": relationship_rows,
            },
        ],
        "scores": {
            "envelope": round(envelope_score, 3),
            "visibility": round(visibility_score, 3),
            "relationships": round(relationship_score, 3),
        },
        "views": views,
        "regeneration_plan": {
            "recommended": not passed,
            "scopes": sorted(failed_scopes),
            "strategy": "replace_failed_requirement_groups",
        },
        "report_file": "multiview_validation.json",
    }
    (output_dir.parent / "multiview_validation.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return report
