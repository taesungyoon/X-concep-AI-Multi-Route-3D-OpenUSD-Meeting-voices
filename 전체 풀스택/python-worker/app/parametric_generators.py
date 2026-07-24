"""Deterministic OpenSCAD-oriented parametric generation contracts.

The legacy generic ``openscad`` mode remains available. Specialized
``part``, ``module``, and ``equipment`` modes convert DesignState into explicit
components/features, support scoped regeneration, and emit reproducible SCAD.
All geometry dimensions use millimetres and a Z-up coordinate convention.
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
from collections import Counter
from typing import Any

from .generator import Part


# Increment when contract geometry changes so datasets/artifacts remain traceable.
GENERATOR_VERSION = "1.2.0"

# Public route values used by the UI, router, persisted plans, and training data.
GENERIC_MODE = "openscad"
AUTO_MODE = "openscad_auto"
PART_MODE = "openscad_part"
MODULE_MODE = "openscad_module"
EQUIPMENT_MODE = "openscad_equipment"
OPENSCAD_GENERATOR_MODES = {GENERIC_MODE, AUTO_MODE, PART_MODE, MODULE_MODE, EQUIPMENT_MODE}
SPECIALIZED_MODES = {PART_MODE, MODULE_MODE, EQUIPMENT_MODE}

# Minimum visual/detail evidence expected for common industrial subassemblies.
EQUIPMENT_DETAIL_EXPECTATIONS: dict[str, tuple[tuple[str, int], ...]] = {
    "conveyor": (
        ("conveyor_side_rail", 2),
        ("conveyor_support_leg", 4),
    ),
    "vision_camera": (("camera_lens", 2),),
    "control_panel": (
        ("control_panel_door", 1),
        ("hmi_screen", 1),
        ("panel_handle", 1),
        ("emergency_stop", 1),
    ),
    "safety_door": (
        ("safety_door_frame", 4),
        ("safety_door_handle", 1),
    ),
}

MODE_FOR_CATEGORY = {
    "part": PART_MODE,
    "module": MODULE_MODE,
    "equipment": EQUIPMENT_MODE,
}

COMPONENT_ALIASES: dict[str, tuple[str, ...]] = {
    "conveyor": ("컨베이어", "conveyor"),
    "servo_motor": ("서보모터", "서보 모터", "servo motor", "servo"),
    "vision_camera": ("비전 카메라", "비전카메라", "vision camera", "camera", "카메라"),
    "control_panel": ("제어반", "control panel", "control cabinet"),
    "safety_door": ("안전도어", "안전 도어", "안전문", "safety door"),
    "safety_cover": ("안전커버", "안전 커버", "safety cover", "투명 커버"),
    "linear_guide": ("리니어 가이드", "리니어가이드", "linear guide", "linear rail"),
    "cylinder": ("실린더", "cylinder"),
    "sensor": ("센서", "sensor"),
    "motor": ("모터", "motor"),
    "working_jig": ("지그", "jig", "작업부", "work unit"),
}

FEATURE_ALIASES: dict[str, tuple[str, ...]] = {
    "mounting_hole": ("체결 홀", "체결홀", "마운팅 홀", "mounting hole", "bolt hole"),
    "sensor_hole": ("센서 홀", "센서홀", "sensor hole"),
    "rib": ("삼각 리브", "리브", "rib", "gusset"),
    "slot": ("장공", "슬롯", "slot"),
    "cutout": ("컷아웃", "개구부", "cutout", "opening"),
}

COUNT_WORDS = {
    "한": 1, "하나": 1, "한개": 1, "한대": 1,
    "두": 2, "둘": 2, "두개": 2, "두대": 2, "양측": 2,
    "세": 3, "셋": 3, "세개": 3, "세대": 3,
    "네": 4, "넷": 4, "네개": 4, "네대": 4,
}


def resolve_generator_mode(requested_mode: str | None, category: str) -> str:
    """Resolve auto mode by category while preserving the generic fallback."""
    mode = requested_mode or GENERIC_MODE
    if mode == AUTO_MODE:
        return MODE_FOR_CATEGORY[category]
    if mode not in OPENSCAD_GENERATOR_MODES:
        return GENERIC_MODE
    return mode


def is_openscad_mode(value: str | None) -> bool:
    return value in OPENSCAD_GENERATOR_MODES


def _contains(text: str, aliases: tuple[str, ...]) -> bool:
    lower = text.lower()
    return any(alias.lower() in lower for alias in aliases)


def _count_near_alias(text: str, aliases: tuple[str, ...], default: int = 1) -> int:
    lower = text.lower()
    for alias in sorted(aliases, key=len, reverse=True):
        token = re.escape(alias.lower())
        patterns = (
            rf"{token}\s*(?:은|는|이|가|:|=)?\s*(\d+)\s*(?:개|대|ea|pcs?)?",
            rf"(\d+)\s*(?:개|대|ea|pcs?)?\s*(?:의\s*)?{token}",
        )
        for pattern in patterns:
            match = re.search(pattern, lower, re.IGNORECASE)
            if match:
                return max(1, min(int(match.group(1)), 64))
        for word, count in COUNT_WORDS.items():
            if re.search(rf"(?:{re.escape(word)}\s*(?:개|대)?\s*{token}|{token}\s*{re.escape(word)}\s*(?:개|대)?)", lower):
                return count
    return default


def _kind_for_name(value: str) -> str | None:
    lower = value.lower()
    for kind, aliases in COMPONENT_ALIASES.items():
        if any(alias.lower() in lower for alias in aliases):
            if kind == "motor" and any(alias in lower for alias in ("servo", "서보")):
                continue
            return kind
    return None


def _feature_count(prompt: str, feature: str, default: int) -> int:
    aliases = FEATURE_ALIASES[feature]
    return _count_near_alias(prompt, aliases, default) if _contains(prompt, aliases) else 0


def _part_mount_target_kinds(prompt: str) -> set[str]:
    """Return referenced equipment that is a mount target, not part geometry."""
    lower = prompt.lower()
    ignored: set[str] = set()
    for kind, aliases in COMPONENT_ALIASES.items():
        explicitly_included = any(
            re.search(rf"{re.escape(alias.lower())}\s*(?:포함|내장|부착|included|installed)", lower)
            for alias in aliases
        )
        if explicitly_included:
            continue
        if any(
            re.search(
                rf"{re.escape(alias.lower())}\s*(?:용\s*)?[\w가-힣 -]{{0,20}}?(?:브래킷|브라켓|홀|마운트|거치대|bracket|hole|mount|holder)",
                lower,
            )
            for alias in aliases
        ):
            ignored.add(kind)
    return ignored


def build_design_spec(design_state: dict[str, Any], category: str) -> dict[str, Any]:
    """Normalize requirements into deterministic component/feature quantities."""
    prompt = str(design_state.get("source_prompt") or "")
    mount_target_kinds = _part_mount_target_kinds(prompt) if category == "part" else set()
    detected: list[dict[str, Any]] = []
    detected_kinds: set[str] = set()
    for kind, aliases in COMPONENT_ALIASES.items():
        if kind in mount_target_kinds:
            continue
        if kind == "motor" and "servo_motor" in detected_kinds:
            continue
        if not _contains(prompt, aliases):
            continue
        quantity = _count_near_alias(prompt, aliases)
        detected.append({
            "id": kind,
            "kind": kind,
            "name": kind.replace("_", " "),
            "quantity": quantity,
            "required": True,
            "source": "prompt",
        })
        detected_kinds.add(kind)

    analysis_components: list[dict[str, Any]] = []
    for index, raw in enumerate(design_state.get("components") or []):
        # Generic design-state fallbacks are useful for the legacy template,
        # but they are not user requirements and must not become hard
        # constraints in a specialized parametric contract.
        source = str(raw.get("source") or "analysis")
        if source == "default":
            continue
        name = str(raw.get("name") or raw.get("id") or f"component_{index + 1}")
        kind = str(raw.get("kind") or _kind_for_name(name) or raw.get("id") or "component")
        if source == "analysis":
            # LLM/mock analysis can supply generic boilerplate such as
            # base_frame/work_unit/drive_unit/control_box even when the user
            # never requested those items. A specialized contract only
            # promotes analysis output when its literal name/id is grounded
            # in the source prompt; known aliases were captured above.
            prompt_lower = prompt.lower()
            grounding_terms = {
                name.lower().strip(),
                str(raw.get("id") or "").lower().replace("_", " ").strip(),
                kind.lower().replace("_", " ").strip(),
            }
            if not any(term and term in prompt_lower for term in grounding_terms):
                continue
        if kind in mount_target_kinds:
            continue
        if kind in detected_kinds:
            continue
        analysis_components.append({
            "id": str(raw.get("id") or kind),
            "kind": kind,
            "name": name,
            "quantity": max(1, int(raw.get("quantity") or raw.get("count") or 1)),
            "required": bool(raw.get("required", True)),
            "source": source,
        })

    core_kind = {"part": "main_body", "module": "base_plate", "equipment": "frame"}[category]
    components = [{
        "id": core_kind,
        "kind": core_kind,
        "name": core_kind.replace("_", " "),
        "quantity": 1,
        "required": True,
        "source": "generator_contract",
    }, *detected, *analysis_components]

    deduplicated: list[dict[str, Any]] = []
    seen: set[str] = set()
    for component in components:
        key = str(component["kind"])
        if key in seen:
            continue
        seen.add(key)
        deduplicated.append(component)

    features: list[dict[str, Any]] = []
    for feature, default in (("mounting_hole", 4), ("sensor_hole", 1), ("rib", 2), ("slot", 1), ("cutout", 1)):
        count = _feature_count(prompt, feature, default)
        if count:
            features.append({
                "id": feature,
                "kind": feature,
                "count": count,
                "required": True,
                "source": "prompt",
            })

    relationships: list[dict[str, Any]] = []
    lower = prompt.lower()
    if "vision_camera" in seen and "conveyor" in seen and any(value in lower for value in ("위", "above", "상부")):
        relationships.append({"subject": "vision_camera", "relation": "above", "object": "conveyor", "required": True})
    if "control_panel" in seen and any(value in lower for value in ("우측", "오른쪽", "right")):
        relationships.append({"subject": "control_panel", "relation": "right_of", "object": "frame", "required": True})
    if "safety_door" in seen and any(value in lower for value in ("전면", "앞", "front")):
        relationships.append({"subject": "safety_door", "relation": "front_of", "object": "frame", "required": True})

    dimensions = dict(design_state.get("dimensions") or {})
    confidence = {
        "components": 0.95 if detected else 0.60,
        "features": 0.95 if features else 0.55,
        "relationships": 0.90 if relationships else 0.55,
        "dimensions": 0.95 if any(value for value in dimensions.values()) else 0.50,
    }
    assumptions: list[str] = []
    if not any(value for value in dimensions.values()):
        assumptions.append("명시 치수가 없어 카테고리 기본 외곽 치수를 사용함")
    if category == "part" and not features:
        assumptions.append("가공 특징이 명시되지 않아 기본 체결 홀과 리브를 사용함")

    return {
        "schema_version": "1.0",
        "category": category,
        "units": "mm",
        "coordinate_system": design_state.get("coordinate_system") or {"up_axis": "Z", "front_axis": "-Y", "handedness": "right"},
        "components": deduplicated,
        "features": features,
        "relationships": relationships,
        "dimensions": dimensions,
        "materials": list(design_state.get("materials") or []),
        "hard_constraints": [
            {"id": f"component:{item['kind']}", "required_count": item["quantity"]}
            for item in deduplicated if item.get("required", True)
        ] + [
            {"id": f"feature:{item['kind']}", "required_count": item["count"]}
            for item in features if item.get("required", True)
        ],
        "confidence": confidence,
        "assumptions": assumptions,
        "source_prompt_hash": design_state.get("prompt_hash"),
    }


def _safe_dim(value: Any, default: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if number > 0 else default


def _overall(design_spec: dict[str, Any], category: str) -> dict[str, float]:
    defaults = {
        "part": (240.0, 160.0, 120.0),
        "module": (800.0, 600.0, 900.0),
        "equipment": (1600.0, 1000.0, 1800.0),
    }[category]
    dims = design_spec.get("dimensions") or {}
    return {
        "width": _safe_dim(dims.get("width_mm") or dims.get("length_mm"), defaults[0]),
        "depth": _safe_dim(dims.get("depth_mm"), defaults[1]),
        "height": _safe_dim(dims.get("height_mm"), defaults[2]),
    }


def _quantity(spec: dict[str, Any], *kinds: str, default: int = 0) -> int:
    for component in spec.get("components") or []:
        if component.get("kind") in kinds:
            return max(1, int(component.get("quantity") or 1))
    return default


def _feature_quantity(spec: dict[str, Any], kind: str, default: int = 0) -> int:
    for feature in spec.get("features") or []:
        if feature.get("kind") == kind:
            return max(1, int(feature.get("count") or 1))
    return default


def _box(component_id: str, kind: str, size: tuple[float, float, float], center: tuple[float, float, float], material: str, requirement_id: str | None = None) -> dict[str, Any]:
    return {
        "id": component_id,
        "kind": kind,
        "shape": "box",
        "size_mm": [round(value, 4) for value in size],
        "center_mm": [round(value, 4) for value in center],
        "material_preset": material,
        "requirement_id": requirement_id or kind,
    }


def _cylinder(component_id: str, kind: str, diameter: float, height: float, center: tuple[float, float, float], axis: str, material: str, requirement_id: str | None = None) -> dict[str, Any]:
    return {
        "id": component_id,
        "kind": kind,
        "shape": "cylinder",
        "diameter_mm": round(diameter, 4),
        "height_mm": round(height, 4),
        "center_mm": [round(value, 4) for value in center],
        "axis": axis,
        "material_preset": material,
        "requirement_id": requirement_id or kind,
    }


def _part_contract(spec: dict[str, Any], overall: dict[str, float]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, float]]:
    w, d, h = overall["width"], overall["depth"], overall["height"]
    thickness = max(4.0, min(w, d, h) * 0.05)
    rib_count = _feature_quantity(spec, "rib", 2)
    mounting_count = _feature_quantity(spec, "mounting_hole", 4)
    sensor_count = _feature_quantity(spec, "sensor_hole", 1)
    components = [
        _box("base_plate", "main_body", (w, d, thickness), (0, 0, thickness / 2), "brushed_aluminum", "main_body"),
        _box("upright_plate", "main_body", (w, thickness, h - thickness), (0, d / 2 - thickness / 2, thickness + (h - thickness) / 2), "brushed_aluminum", "main_body"),
    ]
    rib_x = [0.0] if rib_count == 1 else [(-w * 0.32 + (w * 0.64 * index / max(rib_count - 1, 1))) for index in range(rib_count)]
    for index, x in enumerate(rib_x, start=1):
        components.append(_box(f"rib_{index}", "rib", (thickness * 1.5, d * 0.42, h * 0.46), (x, d * 0.28, thickness + h * 0.23), "brushed_aluminum", "rib"))

    features: list[dict[str, Any]] = []
    hole_positions = [
        (-w * 0.36, -d * 0.30), (w * 0.36, -d * 0.30),
        (-w * 0.36, d * 0.12), (w * 0.36, d * 0.12),
    ]
    for index in range(mounting_count):
        x, y = hole_positions[index % len(hole_positions)]
        features.append({"id": f"mounting_hole_{index + 1}", "kind": "mounting_hole", "diameter_mm": max(5.0, min(w, d) * 0.05), "axis": "Z", "center_mm": [x, y, thickness / 2], "requirement_id": "mounting_hole"})
    for index in range(sensor_count):
        offset = (index - (sensor_count - 1) / 2) * w * 0.24
        features.append({"id": f"sensor_hole_{index + 1}", "kind": "sensor_hole", "diameter_mm": max(24.0, min(w, h) * 0.28), "axis": "Y", "center_mm": [offset, d / 2 - thickness / 2, h * 0.62], "requirement_id": "sensor_hole"})
    return components, features, {"plate_thickness": thickness, "rib_count": float(rib_count)}


def _module_contract(spec: dict[str, Any], overall: dict[str, float]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, float]]:
    w, d, h = overall["width"], overall["depth"], overall["height"]
    plate = max(10.0, min(w, d) * 0.035)
    rail_w, rail_h = max(18.0, d * 0.04), max(18.0, h * 0.035)
    support = max(24.0, min(w, d, h) * 0.045)
    components = [_box("base_plate", "base_plate", (w, d, plate), (0, 0, plate / 2), "painted_steel")]
    for index, x in enumerate((-w * 0.38, w * 0.38), start=1):
        components.append(_box(
            f"gantry_post_{index}", "module_frame", (support, support, h - plate),
            (x, d * 0.34, plate + (h - plate) / 2), "painted_steel", "module_frame",
        ))
    components.append(_box(
        "gantry_top", "module_frame", (w * 0.76 + support, support, support),
        (0, d * 0.34, h - support / 2), "painted_steel", "module_frame",
    ))
    for index, y in enumerate((-d * 0.22, d * 0.22), start=1):
        components.append(_box(f"linear_guide_{index}", "linear_guide", (w * 0.72, rail_w, rail_h), (0, y, plate + rail_h / 2), "hardened_steel", "linear_guide"))
    motor_count = _quantity(spec, "servo_motor", "motor", default=1)
    for index in range(motor_count):
        x = (-w * 0.26) + index * min(w * 0.26, 130.0)
        components.append(_box(f"servo_motor_{index + 1}", "servo_motor", (90.0, 90.0, 110.0), (x, -d * 0.34, plate + 55.0), "industrial_black", "servo_motor"))
    components.append(_box("working_jig", "working_jig", (w * 0.30, d * 0.30, h * 0.16), (w * 0.12, 0, plate + rail_h + h * 0.08), "industrial_blue", "working_jig"))
    sensor_count = _quantity(spec, "sensor", default=0)
    vision_count = _quantity(spec, "vision_camera", default=0)
    if sensor_count == 0 and vision_count == 0:
        sensor_count = 1
    for index in range(sensor_count):
        x = (index - (sensor_count - 1) / 2) * 70.0
        components.append(_box(f"sensor_{index + 1}", "sensor", (45.0, 35.0, 35.0), (x, d * 0.12, h * 0.58), "sensor_black", "sensor"))
        components.append(_box(f"sensor_mount_{index + 1}", "sensor_mount", (20.0, 20.0, h * 0.42), (x, d * 0.12, h * 0.36), "painted_steel", "sensor"))
    for index in range(vision_count):
        x = (index - (vision_count - 1) / 2) * 90.0
        components.append(_box(f"vision_camera_{index + 1}", "vision_camera", (70.0, 55.0, 50.0), (x, d * 0.12, h * 0.60), "sensor_black", "vision_camera"))
        components.append(_box(f"camera_mount_{index + 1}", "camera_mount", (24.0, 24.0, h * 0.44), (x, d * 0.12, h * 0.37), "painted_steel", "vision_camera"))
    return components, [], {"base_plate_thickness": plate, "rail_width": rail_w, "rail_height": rail_h, "support_profile": support}


def _equipment_standard_contract(spec: dict[str, Any], overall: dict[str, float]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, float]]:
    w, d, h = overall["width"], overall["depth"], overall["height"]
    profile = max(30.0, min(w, d, h) * 0.035)
    x, y = w / 2 - profile / 2, d / 2 - profile / 2
    components: list[dict[str, Any]] = []
    for index, (px, py) in enumerate(((-x, -y), (x, -y), (-x, y), (x, y)), start=1):
        components.append(_box(f"frame_post_{index}", "frame", (profile, profile, h), (px, py, h / 2), "aluminum_profile", "frame"))
    for z, prefix in ((profile / 2, "bottom"), (h - profile / 2, "top")):
        components.extend([
            _box(f"frame_{prefix}_front", "frame", (w, profile, profile), (0, -y, z), "aluminum_profile", "frame"),
            _box(f"frame_{prefix}_back", "frame", (w, profile, profile), (0, y, z), "aluminum_profile", "frame"),
            _box(f"frame_{prefix}_left", "frame", (profile, d, profile), (-x, 0, z), "aluminum_profile", "frame"),
            _box(f"frame_{prefix}_right", "frame", (profile, d, profile), (x, 0, z), "aluminum_profile", "frame"),
        ])

    if _quantity(spec, "conveyor", default=1):
        conveyor_w = w * 0.66
        conveyor_d = d * 0.34
        conveyor_h = max(80.0, h * 0.06)
        conveyor_x = -w * 0.04
        conveyor_z = h * 0.42
        components.append(_box("conveyor_1", "conveyor", (conveyor_w, conveyor_d, conveyor_h), (conveyor_x, 0, conveyor_z), "conveyor_steel", "conveyor"))
        for index in range(6):
            rx = -w * 0.28 + index * (w * 0.56 / 5)
            components.append(_cylinder(f"conveyor_roller_{index + 1}", "conveyor_roller", max(24.0, h * 0.025), d * 0.30, (rx, 0, h * 0.46), "Y", "conveyor_roller", "conveyor"))
        rail_h = max(50.0, h * 0.035)
        rail_t = max(18.0, profile * 0.55)
        for index, rail_y in enumerate((-conveyor_d * 0.47, conveyor_d * 0.47), start=1):
            components.append(_box(
                f"conveyor_side_rail_{index}",
                "conveyor_side_rail",
                (conveyor_w, rail_t, rail_h),
                (conveyor_x, rail_y, conveyor_z + conveyor_h / 2 + rail_h / 2),
                "brushed_aluminum",
                "conveyor",
            ))
        leg_h = max(120.0, conveyor_z - conveyor_h / 2)
        for index, (leg_x, leg_y) in enumerate((
            (conveyor_x - conveyor_w * 0.36, -conveyor_d * 0.34),
            (conveyor_x - conveyor_w * 0.36, conveyor_d * 0.34),
            (conveyor_x + conveyor_w * 0.36, -conveyor_d * 0.34),
            (conveyor_x + conveyor_w * 0.36, conveyor_d * 0.34),
        ), start=1):
            components.append(_box(
                f"conveyor_support_leg_{index}",
                "conveyor_support_leg",
                (profile, profile, leg_h),
                (leg_x, leg_y, leg_h / 2),
                "brushed_aluminum",
                "conveyor",
            ))

    motor_count = _quantity(spec, "servo_motor", "motor", default=1)
    for index in range(motor_count):
        mx = -w * 0.22 + index * min(w * 0.22, 180.0)
        components.append(_box(f"servo_motor_{index + 1}", "servo_motor", (110.0, 100.0, 120.0), (mx, d * 0.22, h * 0.30), "industrial_black", "servo_motor"))

    if _quantity(spec, "vision_camera", default=1):
        components.extend([
            _box("camera_mount", "camera_mount", (profile, profile, h * 0.32), (0, 0, h * 0.69), "painted_steel", "vision_camera"),
            _box("vision_camera_1", "vision_camera", (120.0, 90.0, 85.0), (0, 0, h * 0.84), "sensor_black", "vision_camera"),
            _cylinder("camera_lens_1", "camera_lens", 34.0, 30.0, (-28.0, -60.0, h * 0.84), "Y", "glass", "vision_camera"),
            _cylinder("camera_lens_2", "camera_lens", 34.0, 30.0, (28.0, -60.0, h * 0.84), "Y", "glass", "vision_camera"),
        ])

    if _quantity(spec, "safety_door", default=0):
        door_h = h * 0.66
        door_w = w * 0.78
        door_t = max(6.0, profile * 0.18)
        door_y = -d / 2 + profile * 0.65
        door_z = h * 0.56
        door_frame = max(24.0, profile * 0.72)
        components.append(_box("front_safety_door", "safety_door", (door_w, door_t, door_h), (0, door_y, door_z), "transparent_polycarbonate", "safety_door"))
        components.extend([
            _box("door_frame_left", "safety_door_frame", (door_frame, door_t * 1.7, door_h), (-door_w / 2 + door_frame / 2, door_y - door_t * 0.15, door_z), "brushed_aluminum", "safety_door"),
            _box("door_frame_right", "safety_door_frame", (door_frame, door_t * 1.7, door_h), (door_w / 2 - door_frame / 2, door_y - door_t * 0.15, door_z), "brushed_aluminum", "safety_door"),
            _box("door_frame_top", "safety_door_frame", (door_w, door_t * 1.7, door_frame), (0, door_y - door_t * 0.15, door_z + door_h / 2 - door_frame / 2), "brushed_aluminum", "safety_door"),
            _box("door_frame_bottom", "safety_door_frame", (door_w, door_t * 1.7, door_frame), (0, door_y - door_t * 0.15, door_z - door_h / 2 + door_frame / 2), "brushed_aluminum", "safety_door"),
            _box("door_handle", "safety_door_handle", (24.0, max(20.0, door_t * 3.0), 180.0), (door_w * 0.34, door_y - max(14.0, door_t * 1.5), door_z), "industrial_black", "safety_door"),
        ])
    if _quantity(spec, "safety_cover", default=0):
        cover_t = max(5.0, profile * 0.16)
        cover_h = h * 0.66
        cover_z = h * 0.56
        components.extend([
            _box("safety_cover_left", "safety_cover", (cover_t, d * 0.78, cover_h), (-w / 2 + profile * 0.65, 0, cover_z), "transparent_polycarbonate", "safety_cover"),
            _box("safety_cover_right", "safety_cover", (cover_t, d * 0.78, cover_h), (w / 2 - profile * 0.65, 0, cover_z), "transparent_polycarbonate", "safety_cover"),
            _box("safety_cover_rear", "safety_cover", (w * 0.78, cover_t, cover_h), (0, d / 2 - profile * 0.65, cover_z), "transparent_polycarbonate", "safety_cover"),
        ])
    if _quantity(spec, "control_panel", default=1):
        panel_w, panel_d, panel_h = w * 0.18, d * 0.28, h * 0.48
        panel_x = w / 2 - profile - panel_w / 2
        panel_front_y = -panel_d / 2
        components.extend([
            _box("control_panel_1", "control_panel", (panel_w, panel_d, panel_h), (panel_x, 0, panel_h / 2), "control_gray", "control_panel"),
            _box("control_panel_door", "control_panel_door", (panel_w * 0.86, max(8.0, profile * 0.28), panel_h * 0.88), (panel_x, panel_front_y - max(4.0, profile * 0.14), panel_h * 0.50), "painted_steel", "control_panel"),
            _box("hmi_screen", "hmi_screen", (panel_w * 0.52, max(8.0, profile * 0.34), panel_h * 0.22), (panel_x, panel_front_y - max(10.0, profile * 0.31), panel_h * 0.67), "hmi_blue", "control_panel"),
            _box("panel_handle", "panel_handle", (20.0, max(18.0, profile * 0.60), panel_h * 0.20), (panel_x + panel_w * 0.34, panel_front_y - max(16.0, profile * 0.46), panel_h * 0.40), "industrial_black", "control_panel"),
            _cylinder("emergency_stop", "emergency_stop", max(34.0, profile), max(18.0, profile * 0.60), (panel_x - panel_w * 0.27, panel_front_y - max(18.0, profile * 0.54), panel_h * 0.45), "Y", "emergency_red", "control_panel"),
        ])

    return components, [], {"frame_profile": profile, "layout_variant": "standard_cell"}


def _inspection_cell_contract(spec: dict[str, Any], overall: dict[str, float]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, float]]:
    """Vision-inspection cell with an external cabinet and front conveyor."""
    w, d, h = overall["width"], overall["depth"], overall["height"]
    profile = max(30.0, min(w, d, h) * 0.032)
    cell_left = -w / 2
    cell_right = w * 0.22
    cell_front = -d * 0.22
    cell_back = d / 2
    cell_width = cell_right - cell_left
    cell_depth = cell_back - cell_front
    cell_center_x = (cell_left + cell_right) / 2
    cell_center_y = (cell_front + cell_back) / 2
    cell_top = h * 0.78
    components: list[dict[str, Any]] = []

    post_x = (cell_left + profile / 2, cell_right - profile / 2)
    post_y = (cell_front + profile / 2, cell_back - profile / 2)
    for index, (px, py) in enumerate(
        ((post_x[0], post_y[0]), (post_x[1], post_y[0]), (post_x[0], post_y[1]), (post_x[1], post_y[1])),
        start=1,
    ):
        components.append(
            _box(
                f"frame_post_{index}",
                "frame",
                (profile, profile, cell_top),
                (px, py, cell_top / 2),
                "aluminum_profile",
                "frame",
            )
        )
    for z, prefix in ((profile / 2, "bottom"), (cell_top - profile / 2, "top")):
        components.extend([
            _box(f"frame_{prefix}_front", "frame", (cell_width, profile, profile), (cell_center_x, post_y[0], z), "aluminum_profile", "frame"),
            _box(f"frame_{prefix}_back", "frame", (cell_width, profile, profile), (cell_center_x, post_y[1], z), "aluminum_profile", "frame"),
            _box(f"frame_{prefix}_left", "frame", (profile, cell_depth, profile), (post_x[0], cell_center_y, z), "aluminum_profile", "frame"),
            _box(f"frame_{prefix}_right", "frame", (profile, cell_depth, profile), (post_x[1], cell_center_y, z), "aluminum_profile", "frame"),
        ])
    lower_beam_z = h * 0.34
    components.extend([
        _box("frame_mid_front", "frame", (cell_width, profile, profile), (cell_center_x, post_y[0], lower_beam_z), "aluminum_profile", "frame"),
        _box("frame_mid_back", "frame", (cell_width, profile, profile), (cell_center_x, post_y[1], lower_beam_z), "aluminum_profile", "frame"),
    ])

    if _quantity(spec, "conveyor", default=1):
        conveyor_w = cell_width * 0.54
        conveyor_d = d * 0.78
        conveyor_h = max(80.0, h * 0.055)
        conveyor_x = cell_center_x - cell_width * 0.08
        conveyor_y = -d * 0.11
        conveyor_z = h * 0.38
        components.append(
            _box("conveyor_1", "conveyor", (conveyor_w, conveyor_d, conveyor_h), (conveyor_x, conveyor_y, conveyor_z), "conveyor_steel", "conveyor")
        )
        for index in range(6):
            roller_y = conveyor_y - conveyor_d * 0.38 + index * (conveyor_d * 0.76 / 5)
            components.append(
                _cylinder(
                    f"conveyor_roller_{index + 1}",
                    "conveyor_roller",
                    max(24.0, h * 0.024),
                    conveyor_w * 0.90,
                    (conveyor_x, roller_y, conveyor_z + conveyor_h * 0.63),
                    "X",
                    "conveyor_roller",
                    "conveyor",
                )
            )
        rail_h = max(50.0, h * 0.035)
        rail_t = max(18.0, profile * 0.55)
        for index, rail_x in enumerate((conveyor_x - conveyor_w * 0.48, conveyor_x + conveyor_w * 0.48), start=1):
            components.append(
                _box(
                    f"conveyor_side_rail_{index}",
                    "conveyor_side_rail",
                    (rail_t, conveyor_d, rail_h),
                    (rail_x, conveyor_y, conveyor_z + conveyor_h / 2 + rail_h / 2),
                    "brushed_aluminum",
                    "conveyor",
                )
            )
        leg_h = max(120.0, conveyor_z - conveyor_h / 2)
        for index, (leg_x, leg_y) in enumerate((
            (conveyor_x - conveyor_w * 0.38, -d * 0.39),
            (conveyor_x + conveyor_w * 0.38, -d * 0.39),
            (conveyor_x - conveyor_w * 0.38, d * 0.14),
            (conveyor_x + conveyor_w * 0.38, d * 0.14),
        ), start=1):
            components.append(
                _box(
                    f"conveyor_support_leg_{index}",
                    "conveyor_support_leg",
                    (profile, profile, leg_h),
                    (leg_x, leg_y, leg_h / 2),
                    "brushed_aluminum",
                    "conveyor",
                )
            )

    motor_count = _quantity(spec, "servo_motor", "motor", default=1)
    for index in range(motor_count):
        motor_y = -d * 0.24 + index * min(d * 0.22, 180.0)
        components.append(
            _box(
                f"servo_motor_{index + 1}",
                "servo_motor",
                (110.0, 105.0, 120.0),
                (cell_center_x + cell_width * 0.23, motor_y, h * 0.29),
                "industrial_black",
                "servo_motor",
            )
        )

    if _quantity(spec, "vision_camera", default=1):
        camera_z = h - 75.0
        components.extend([
            _box("camera_bridge", "camera_mount", (cell_width * 0.36, profile, profile), (cell_center_x, cell_center_y, cell_top + profile), "painted_steel", "vision_camera"),
            _box("camera_mount", "camera_mount", (profile, profile, h * 0.13), (cell_center_x, cell_center_y, cell_top + h * 0.065), "painted_steel", "vision_camera"),
            _box("vision_camera_1", "vision_camera", (150.0, 105.0, 150.0), (cell_center_x, cell_center_y, camera_z), "sensor_black", "vision_camera"),
            _box("camera_sensor_left", "camera_sensor_module", (95.0, 90.0, 120.0), (cell_center_x - 125.0, cell_center_y, camera_z - 10.0), "sensor_black", "vision_camera"),
            _box("camera_sensor_right", "camera_sensor_module", (95.0, 90.0, 120.0), (cell_center_x + 125.0, cell_center_y, camera_z - 10.0), "sensor_black", "vision_camera"),
            _cylinder("camera_lens_1", "camera_lens", 42.0, 48.0, (cell_center_x - 125.0, cell_center_y - 64.0, camera_z - 10.0), "Y", "glass", "vision_camera"),
            _cylinder("camera_lens_2", "camera_lens", 42.0, 48.0, (cell_center_x + 125.0, cell_center_y - 64.0, camera_z - 10.0), "Y", "glass", "vision_camera"),
            _cylinder("inspection_optic", "camera_optic", 72.0, 100.0, (cell_center_x, cell_center_y, camera_z - 120.0), "Z", "glass", "vision_camera"),
        ])

    if _quantity(spec, "safety_door", default=0):
        door_w = cell_width * 0.84
        door_h = h * 0.36
        door_t = max(6.0, profile * 0.18)
        door_y = cell_front - door_t / 2
        door_z = h * 0.57
        door_frame = max(24.0, profile * 0.72)
        components.append(_box("front_safety_door", "safety_door", (door_w, door_t, door_h), (cell_center_x, door_y, door_z), "transparent_polycarbonate", "safety_door"))
        components.extend([
            _box("door_frame_left", "safety_door_frame", (door_frame, door_t * 1.7, door_h), (cell_center_x - door_w / 2 + door_frame / 2, door_y - door_t * 0.15, door_z), "brushed_aluminum", "safety_door"),
            _box("door_frame_right", "safety_door_frame", (door_frame, door_t * 1.7, door_h), (cell_center_x + door_w / 2 - door_frame / 2, door_y - door_t * 0.15, door_z), "brushed_aluminum", "safety_door"),
            _box("door_frame_top", "safety_door_frame", (door_w, door_t * 1.7, door_frame), (cell_center_x, door_y - door_t * 0.15, door_z + door_h / 2 - door_frame / 2), "brushed_aluminum", "safety_door"),
            _box("door_frame_bottom", "safety_door_frame", (door_w, door_t * 1.7, door_frame), (cell_center_x, door_y - door_t * 0.15, door_z - door_h / 2 + door_frame / 2), "brushed_aluminum", "safety_door"),
            _box("door_handle", "safety_door_handle", (24.0, max(20.0, door_t * 3.0), 180.0), (cell_center_x + door_w * 0.34, door_y - max(14.0, door_t * 1.5), door_z), "industrial_black", "safety_door"),
            _box("door_hinge_top", "safety_door_hinge", (28.0, max(22.0, door_t * 3.4), 70.0), (cell_center_x - door_w * 0.48, door_y - max(15.0, door_t * 1.7), door_z + door_h * 0.28), "industrial_black", "safety_door"),
            _box("door_hinge_bottom", "safety_door_hinge", (28.0, max(22.0, door_t * 3.4), 70.0), (cell_center_x - door_w * 0.48, door_y - max(15.0, door_t * 1.7), door_z - door_h * 0.28), "industrial_black", "safety_door"),
        ])
    if _quantity(spec, "safety_cover", default=0):
        cover_t = max(5.0, profile * 0.16)
        cover_h = h * 0.42
        cover_z = h * 0.56
        components.extend([
            _box("safety_cover_left", "safety_cover", (cover_t, cell_depth * 0.90, cover_h), (cell_left + profile * 0.65, cell_center_y, cover_z), "transparent_polycarbonate", "safety_cover"),
            _box("safety_cover_right", "safety_cover", (cover_t, cell_depth * 0.90, cover_h), (cell_right - profile * 0.65, cell_center_y, cover_z), "transparent_polycarbonate", "safety_cover"),
            _box("safety_cover_rear", "safety_cover", (cell_width * 0.90, cover_t, cover_h), (cell_center_x, cell_back - profile * 0.65, cover_z), "transparent_polycarbonate", "safety_cover"),
        ])
    if _quantity(spec, "control_panel", default=1):
        panel_w, panel_d, panel_h = w * 0.18, d * 0.32, h * 0.58
        panel_x = w / 2 - panel_w / 2
        panel_y = -d * 0.08
        panel_front_y = panel_y - panel_d / 2
        components.extend([
            _box("control_panel_1", "control_panel", (panel_w, panel_d, panel_h), (panel_x, panel_y, panel_h / 2), "control_gray", "control_panel"),
            _box("control_panel_door", "control_panel_door", (panel_w * 0.86, max(8.0, profile * 0.28), panel_h * 0.88), (panel_x, panel_front_y - max(4.0, profile * 0.14), panel_h * 0.50), "painted_steel", "control_panel"),
            _box("hmi_screen", "hmi_screen", (panel_w * 0.52, max(8.0, profile * 0.34), panel_h * 0.22), (panel_x, panel_front_y - max(10.0, profile * 0.31), panel_h * 0.67), "hmi_blue", "control_panel"),
            _box("panel_handle", "panel_handle", (20.0, max(18.0, profile * 0.60), panel_h * 0.20), (panel_x + panel_w * 0.34, panel_front_y - max(16.0, profile * 0.46), panel_h * 0.40), "industrial_black", "control_panel"),
            _cylinder("emergency_stop", "emergency_stop", max(34.0, profile), max(18.0, profile * 0.60), (panel_x - panel_w * 0.27, panel_front_y - max(18.0, profile * 0.54), panel_h * 0.45), "Y", "emergency_red", "control_panel"),
            _cylinder("status_button_green", "status_button", 20.0, max(14.0, profile * 0.42), (panel_x - panel_w * 0.08, panel_front_y - max(17.0, profile * 0.50), panel_h * 0.45), "Y", "status_green", "control_panel"),
            _cylinder("status_button_amber", "status_button", 20.0, max(14.0, profile * 0.42), (panel_x + panel_w * 0.08, panel_front_y - max(17.0, profile * 0.50), panel_h * 0.45), "Y", "status_amber", "control_panel"),
        ])

    return components, [], {
        "frame_profile": profile,
        "layout_variant": "vision_inspection_cell",
        "cell_envelope": {
            "left": cell_left,
            "right": cell_right,
            "front": cell_front,
            "back": cell_back,
            "top": cell_top,
        },
    }


def _equipment_contract(
    spec: dict[str, Any],
    overall: dict[str, float],
    source_prompt: str = "",
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, float]]:
    normalized = source_prompt.lower()
    inspection_terms = (
        "vision inspection",
        "visual inspection",
        "vision camera",
        "비전 검사",
        "비전검사",
        "비전 카메라",
        "검사 설비",
        "검사설비",
    )
    if any(term in normalized for term in inspection_terms):
        return _inspection_cell_contract(spec, overall)
    return _equipment_standard_contract(spec, overall)


def _coverage(spec: dict[str, Any], components: list[dict[str, Any]], features: list[dict[str, Any]]) -> dict[str, Any]:
    component_counts = Counter(str(item.get("requirement_id") or item.get("kind")) for item in components)
    feature_counts = Counter(str(item.get("requirement_id") or item.get("kind")) for item in features)
    # Some geometric requirements (for example, a rib) are represented as
    # solid components instead of subtractive feature records. Count those
    # requirement IDs as feature evidence as well, while keeping the concrete
    # feature list reserved for holes, slots, and cut-outs.
    feature_counts.update(
        str(item.get("requirement_id"))
        for item in components
        if item.get("requirement_id")
    )
    component_rows = []
    for item in spec.get("components") or []:
        if not item.get("required", True):
            continue
        required = int(item.get("quantity") or 1)
        represented = int(component_counts.get(str(item.get("kind")), 0))
        component_rows.append({"id": str(item.get("kind")), "required": required, "represented": represented, "passed": represented >= required})
    feature_rows = []
    for item in spec.get("features") or []:
        if not item.get("required", True):
            continue
        required = int(item.get("count") or 1)
        represented = int(feature_counts.get(str(item.get("kind")), 0))
        feature_rows.append({"id": str(item.get("kind")), "required": required, "represented": represented, "passed": represented >= required})
    relationship_rows = []
    represented_kinds = {str(item.get("requirement_id") or item.get("kind")) for item in components}
    for item in spec.get("relationships") or []:
        passed = str(item.get("subject")) in represented_kinds and str(item.get("object")) in represented_kinds
        relationship_rows.append({**item, "passed": passed})
    detail_rows: list[dict[str, Any]] = []
    concrete_kind_counts = Counter(str(item.get("kind") or "") for item in components)
    required_component_kinds = {
        str(item.get("kind"))
        for item in spec.get("components") or []
        if item.get("required", True)
    }
    for parent_kind, expectations in EQUIPMENT_DETAIL_EXPECTATIONS.items():
        if parent_kind not in required_component_kinds:
            continue
        for detail_kind, required in expectations:
            represented = int(concrete_kind_counts.get(detail_kind, 0))
            detail_rows.append({
                "id": f"{parent_kind}:{detail_kind}",
                "parent": parent_kind,
                "kind": detail_kind,
                "required": required,
                "represented": represented,
                "passed": represented >= required,
            })
    return {
        "components": component_rows,
        "features": feature_rows,
        "relationships": relationship_rows,
        "assembly_details": detail_rows,
    }


def build_geometry_contract(design_state: dict[str, Any], category: str, generator_mode: str) -> dict[str, Any]:
    """Create the versioned geometry contract consumed by SCAD and validation."""
    resolved_mode = resolve_generator_mode(generator_mode, category)
    if resolved_mode not in SPECIALIZED_MODES:
        raise ValueError(f"specialized OpenSCAD mode required, got {resolved_mode}")
    spec = design_state.get("design_spec") or build_design_spec(design_state, category)
    overall = _overall(spec, category)
    if resolved_mode == PART_MODE:
        components, features, parameters = _part_contract(spec, overall)
    elif resolved_mode == MODULE_MODE:
        components, features, parameters = _module_contract(spec, overall)
    else:
        components, features, parameters = _equipment_contract(
            spec,
            overall,
            str(design_state.get("source_prompt") or ""),
        )
    coverage = _coverage(spec, components, features)
    seed_source = f"{spec.get('source_prompt_hash')}:{resolved_mode}:{GENERATOR_VERSION}"
    deterministic_seed = int(hashlib.sha256(seed_source.encode("utf-8")).hexdigest()[:16], 16)
    contract: dict[str, Any] = {
        "schema_version": "2.0",
        "generator_mode": resolved_mode,
        "generator_version": GENERATOR_VERSION,
        "units": "mm",
        "coordinate_system": spec.get("coordinate_system"),
        "overall": overall,
        "parameters": parameters,
        "components": components,
        "features": features,
        "relationships": spec.get("relationships") or [],
        "hard_constraints": spec.get("hard_constraints") or [],
        "assumptions": spec.get("assumptions") or [],
        "requirement_coverage": coverage,
        "deterministic_seed": deterministic_seed,
        "design_spec": spec,
    }
    canonical = json.dumps(contract, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    contract["contract_sha256"] = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return contract


def _refresh_contract_hash(contract: dict[str, Any]) -> dict[str, Any]:
    contract = copy.deepcopy(contract)
    contract.pop("contract_sha256", None)
    canonical = json.dumps(contract, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    contract["contract_sha256"] = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return contract


def _scope_token(value: str) -> str:
    return value.strip().split(":", 1)[-1]


def apply_partial_regeneration(
    previous_contract: dict[str, Any],
    candidate_contract: dict[str, Any],
    regeneration_scope: list[str],
) -> dict[str, Any]:
    """Replace only requested component scopes and retain unaffected geometry."""
    selected = {_scope_token(str(value)) for value in regeneration_scope if str(value).strip()}
    if not selected:
        raise ValueError("부분 재생성 범위가 비어 있음")
    if previous_contract.get("generator_mode") != candidate_contract.get("generator_mode"):
        raise ValueError("기존 계약과 신규 계약의 파라메트릭 모드가 다름")

    candidate = copy.deepcopy(candidate_contract)
    available = {
        str(item.get("requirement_id") or item.get("kind") or item.get("id"))
        for key in ("components", "features")
        for item in candidate.get(key) or []
    }
    unknown = sorted(selected - available)
    if unknown:
        raise ValueError(f"부분 재생성 범위가 현재 계약에 없음: {', '.join(unknown)}")

    if previous_contract.get("overall") != candidate.get("overall"):
        candidate["partial_regeneration"] = {
            "requested_scope": sorted(selected),
            "applied": False,
            "fallback": "full_regeneration",
            "reason": "overall_dimensions_changed",
            "base_contract_sha256": previous_contract.get("contract_sha256"),
        }
        return _refresh_contract_hash(candidate)

    def merge_items(key: str) -> tuple[list[dict[str, Any]], list[str], list[str]]:
        previous_by_id = {
            str(item.get("id")): item
            for item in previous_contract.get(key) or []
            if item.get("id")
        }
        merged: list[dict[str, Any]] = []
        regenerated: list[str] = []
        preserved: list[str] = []
        for item in candidate.get(key) or []:
            item_id = str(item.get("id") or "")
            requirement_id = str(item.get("requirement_id") or item.get("kind") or item_id)
            if requirement_id in selected or str(item.get("kind") or "") in selected or item_id in selected:
                merged.append(item)
                regenerated.append(item_id)
            elif item_id in previous_by_id:
                merged.append(copy.deepcopy(previous_by_id[item_id]))
                preserved.append(item_id)
            else:
                merged.append(item)
                regenerated.append(item_id)
        return merged, regenerated, preserved

    components, regenerated_components, preserved_components = merge_items("components")
    features, regenerated_features, preserved_features = merge_items("features")
    candidate["components"] = components
    candidate["features"] = features
    candidate["requirement_coverage"] = _coverage(
        candidate.get("design_spec") or {},
        components,
        features,
    )
    candidate["partial_regeneration"] = {
        "requested_scope": sorted(selected),
        "regenerated_requirement_ids": sorted(selected),
        "applied": True,
        "strategy": "replace_failed_requirement_groups",
        "base_contract_sha256": previous_contract.get("contract_sha256"),
        "regenerated_component_ids": regenerated_components,
        "preserved_component_ids": preserved_components,
        "regenerated_feature_ids": regenerated_features,
        "preserved_feature_ids": preserved_features,
    }
    return _refresh_contract_hash(candidate)


def _scad_number(value: Any) -> str:
    return f"{float(value):.6f}".rstrip("0").rstrip(".")


def _component_scad(component: dict[str, Any]) -> str:
    center = ",".join(_scad_number(value) for value in component["center_mm"])
    if component.get("shape") == "cylinder":
        diameter = _scad_number(component["diameter_mm"])
        height = _scad_number(component["height_mm"])
        rotation = {"X": "[0,90,0]", "Y": "[90,0,0]", "Z": "[0,0,0]"}.get(str(component.get("axis") or "Z").upper(), "[0,0,0]")
        return f"translate([{center}]) rotate({rotation}) cylinder(h={height}, d={diameter}, center=true);"
    size = ",".join(_scad_number(value) for value in component["size_mm"])
    return f"translate([{center}]) cube([{size}], center=true);"


def write_specialized_scad(path: Any, contract: dict[str, Any]) -> None:
    positive = "\n    ".join(_component_scad(item) for item in contract["components"])
    negative_lines: list[str] = []
    for feature in contract.get("features") or []:
        if feature.get("kind") not in {"mounting_hole", "sensor_hole", "slot", "cutout"}:
            continue
        center = ",".join(_scad_number(value) for value in feature["center_mm"])
        diameter = _scad_number(feature.get("diameter_mm") or 10.0)
        axis = str(feature.get("axis") or "Z").upper()
        span = max(contract["overall"].values()) * 2.2
        rotation = {"X": "[0,90,0]", "Y": "[90,0,0]", "Z": "[0,0,0]"}[axis]
        negative_lines.append(f"translate([{center}]) rotate({rotation}) cylinder(h={_scad_number(span)}, d={diameter}, center=true);")
    negative = "\n    ".join(negative_lines)
    body = ["$fn=72;", "difference() {", "  union() {", f"    {positive}", "  }"]
    if negative:
        body.extend([f"  {negative}"])
    body.append("}")
    path.write_text("\n".join(body) + "\n", encoding="utf-8")


def parts_from_contract(contract: dict[str, Any]) -> list[Part]:
    colors = {
        "brushed_aluminum": (170, 178, 184, 255),
        "aluminum_profile": (185, 193, 198, 255),
        "painted_steel": (78, 102, 117, 255),
        "industrial_blue": (27, 112, 178, 255),
        "industrial_black": (28, 34, 39, 255),
        "sensor_black": (20, 24, 28, 255),
        "transparent_polycarbonate": (120, 190, 210, 120),
        "control_gray": (78, 84, 88, 255),
        "conveyor_steel": (110, 120, 126, 255),
        "conveyor_roller": (95, 100, 105, 255),
        "hardened_steel": (105, 112, 118, 255),
        "glass": (35, 62, 75, 255),
        "hmi_blue": (16, 130, 202, 255),
        "emergency_red": (210, 28, 35, 255),
    }
    parts: list[Part] = []
    for item in contract.get("components") or []:
        if item.get("shape") == "cylinder":
            diameter = float(item["diameter_mm"])
            height = float(item["height_mm"])
            axis = str(item.get("axis") or "Z").upper()
            size_mm = (height, diameter, diameter) if axis == "X" else (diameter, height, diameter) if axis == "Y" else (diameter, diameter, height)
        else:
            size_mm = tuple(float(value) for value in item["size_mm"])
        center_mm = tuple(float(value) for value in item["center_mm"])
        parts.append(Part(
            str(item["id"]),
            tuple(value / 1000.0 for value in size_mm),
            tuple(value / 1000.0 for value in center_mm),
            colors.get(str(item.get("material_preset")), (90, 110, 120, 255)),
        ))
    return parts
