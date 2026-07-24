from __future__ import annotations

"""Standalone bootstrap DesignSpec/GeometryContract generation.

This module deliberately has no dependency on the full Xconcep worker. It lets
the portable training ZIP preprocess licensed PHP DXF/STEP packages on another
server. Human-reviewed labels supplied in the raw record always take priority.
"""

import hashlib
import json
import re
from typing import Any


DEFAULT_COMPONENTS = {
    "part": ("main_body", "mounting_feature"),
    "module": ("base_plate", "working_unit", "drive_unit", "sensor_mount"),
    "equipment": ("frame", "working_unit", "drive_unit", "control_panel", "safety_guard"),
}

COMPONENT_TERMS = {
    "frame": ("frame", "프레임"),
    "conveyor": ("conveyor", "컨베이어"),
    "servo_motor": ("servo", "서보"),
    "vision_camera": ("vision camera", "camera", "비전 카메라", "카메라"),
    "safety_door": ("safety door", "안전 도어", "안전도어"),
    "control_panel": ("control panel", "control box", "제어반", "제어 반", "제어함"),
    "sensor": ("sensor", "센서"),
    "jig": ("jig", "지그"),
    "bracket": ("bracket", "브래킷"),
}

FEATURE_TERMS = {
    "hole": ("hole", "구멍", "홀"),
    "slot": ("slot", "슬롯", "장공"),
    "rib": ("rib", "리브", "보강"),
}


def _sha256_json(value: dict[str, Any]) -> str:
    canonical = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _positive_number(value: Any) -> float | None:
    if isinstance(value, (int, float)) and 0 < float(value) < 1_000_000:
        return float(value)
    if isinstance(value, str):
        match = re.search(r"\d+(?:\.\d+)?", value.replace(",", ""))
        if match and 0 < float(match.group()) < 1_000_000:
            return float(match.group())
    return None


def _prompt_dimension(prompt: str, labels: tuple[str, ...]) -> float | None:
    number = r"([0-9][0-9,]*(?:\.[0-9]+)?)"
    unit = r"(mm|cm|m|밀리미터|센티미터|미터)?"
    label = "(?:" + "|".join(re.escape(item) for item in labels) + ")"
    for pattern in (
        rf"{label}\s*(?:은|는|을|를|:|=)?\s*{number}\s*{unit}",
        rf"{number}\s*{unit}\s*(?:의\s*)?{label}",
    ):
        match = re.search(pattern, prompt, re.IGNORECASE)
        if not match:
            continue
        value = float(match.group(1).replace(",", ""))
        parsed_unit = (match.group(2) or "mm").lower()
        multiplier = 1000.0 if parsed_unit in {"m", "미터"} else 10.0 if parsed_unit in {"cm", "센티미터"} else 1.0
        return value * multiplier
    return None


def _observed_extent(raw: dict[str, Any]) -> list[Any]:
    cad_context = raw.get("cad_context") if isinstance(raw.get("cad_context"), dict) else {}
    bbox = cad_context.get("bbox") if isinstance(cad_context.get("bbox"), dict) else {}
    if not bbox:
        source = raw.get("source_analysis") if isinstance(raw.get("source_analysis"), dict) else {}
        observed = source.get("cad_observed") if isinstance(source.get("cad_observed"), dict) else {}
        bbox = observed.get("bbox") if isinstance(observed.get("bbox"), dict) else {}
    extent = bbox.get("extent") if isinstance(bbox.get("extent"), list) else []
    return extent[:3]


def _dimensions(raw: dict[str, Any]) -> dict[str, float | None]:
    prompt = str(raw.get("prompt") or "")
    explicit = raw.get("dimensions") if isinstance(raw.get("dimensions"), dict) else {}
    extent = _observed_extent(raw)
    aliases = {
        "width_mm": ("width_mm", "width", "폭", "가로"),
        "depth_mm": ("depth_mm", "depth", "깊이", "세로"),
        "height_mm": ("height_mm", "height", "높이"),
        "length_mm": ("length_mm", "length", "길이"),
    }
    result: dict[str, float | None] = {}
    for index, (target, keys) in enumerate(aliases.items()):
        value = next((_positive_number(explicit.get(key)) for key in keys if _positive_number(explicit.get(key)) is not None), None)
        value = value or _prompt_dimension(prompt, keys[1:])
        if value is None and index < 3 and index < len(extent):
            value = _positive_number(extent[index])
        result[target] = value
    return result


def _components(raw: dict[str, Any]) -> list[dict[str, Any]]:
    prompt = str(raw.get("prompt") or "").lower()
    category = str(raw["category"])
    selected = list(DEFAULT_COMPONENTS[category])
    for kind, terms in COMPONENT_TERMS.items():
        if any(term.lower() in prompt for term in terms) and kind not in selected:
            selected.append(kind)
    return [
        {
            "id": kind,
            "kind": kind,
            "name": kind.replace("_", " "),
            "quantity": 1,
            "required": True,
            "source": "portable_preprocessor",
        }
        for kind in selected
    ]


def _features(raw: dict[str, Any]) -> list[dict[str, Any]]:
    prompt = str(raw.get("prompt") or "").lower()
    result = []
    for kind, terms in FEATURE_TERMS.items():
        if any(term.lower() in prompt for term in terms):
            result.append(
                {
                    "id": f"feature_{kind}",
                    "kind": kind,
                    "quantity": 1,
                    "required": True,
                    "source": "portable_preprocessor",
                }
            )
    return result


def _bootstrap_design_spec(raw: dict[str, Any]) -> dict[str, Any]:
    prompt = str(raw["prompt"])
    components = _components(raw)
    features = _features(raw)
    dimensions = _dimensions(raw)
    hard_constraints = [
        {"id": f"component:{item['id']}", "required_count": item["quantity"]}
        for item in components
    ]
    hard_constraints.extend(
        {"id": f"feature:{item['id']}", "required_count": item["quantity"]}
        for item in features
    )
    return {
        "schema_version": "1.0",
        "category": raw["category"],
        "units": "mm",
        "coordinate_system": {"up_axis": "Z", "front_axis": "-Y", "handedness": "right"},
        "components": components,
        "features": features,
        "relationships": [],
        "dimensions": dimensions,
        "materials": [],
        "hard_constraints": hard_constraints,
        "confidence": {
            "components": 0.65,
            "features": 0.55,
            "relationships": 0.0,
            "dimensions": 0.85 if any(value is not None for value in dimensions.values()) else 0.0,
        },
        "assumptions": ["portable bootstrap label; production engineer review required"],
        "source_prompt_hash": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
    }


def _bootstrap_contract(
    raw: dict[str, Any],
    design_spec: dict[str, Any],
    generator_mode: str,
) -> dict[str, Any]:
    components = design_spec.get("components") or []
    features = design_spec.get("features") or []
    contract: dict[str, Any] = {
        "schema_version": "xconcep.geometry-contract/1.0",
        "generator_mode": generator_mode,
        "generator_version": "portable-preprocessor-1.0",
        "category": raw["category"],
        "units": "mm",
        "coordinate_system": design_spec["coordinate_system"],
        "dimensions": design_spec["dimensions"],
        "components": components,
        "features": features,
        "relationships": design_spec.get("relationships") or [],
        "hard_constraints": design_spec.get("hard_constraints") or [],
        "requirement_coverage": {
            "components": [
                {
                    "id": item["id"],
                    "required": item.get("quantity", 1),
                    "represented": item.get("quantity", 1),
                    "passed": True,
                }
                for item in components
            ],
            "features": [
                {
                    "id": item["id"],
                    "required": item.get("quantity", 1),
                    "represented": item.get("quantity", 1),
                    "passed": True,
                }
                for item in features
            ],
            "relationships": [],
        },
        "source": {
            "kind": "portable_preprocessor",
            "cad_context": raw.get("cad_context") if isinstance(raw.get("cad_context"), dict) else None,
        },
    }
    contract["contract_sha256"] = _sha256_json(contract)
    return contract


def build_portable_contracts(
    raw: dict[str, Any],
    *,
    generator_mode: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return explicit labels unchanged, otherwise create standalone bootstrap labels."""
    design_spec = raw.get("design_spec") if isinstance(raw.get("design_spec"), dict) else _bootstrap_design_spec(raw)
    contract = (
        raw.get("geometry_contract")
        if isinstance(raw.get("geometry_contract"), dict)
        else _bootstrap_contract(raw, design_spec, generator_mode)
    )
    return design_spec, contract
