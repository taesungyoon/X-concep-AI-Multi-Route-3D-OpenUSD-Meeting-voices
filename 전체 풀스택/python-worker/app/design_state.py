from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from typing import Any

DEFAULT_COMPONENTS = {
    "equipment": ["base_frame", "work_unit", "drive_unit", "control_box", "safety_cover"],
    "module": ["base_plate", "drive_unit", "working_jig", "sensor_mount"],
    "part": ["main_body", "mounting_holes", "functional_surface"],
}

COLOR_ALIASES = {
    "파랑": "blue", "블루": "blue", "blue": "blue",
    "검정": "black", "블랙": "black", "black": "black",
    "회색": "gray", "그레이": "gray", "gray": "gray",
    "흰색": "white", "화이트": "white", "white": "white",
    "빨강": "red", "레드": "red", "red": "red",
    "초록": "green", "그린": "green", "green": "green",
    "노랑": "yellow", "옐로": "yellow", "yellow": "yellow",
}


def _first_number(value: Any) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        match = re.search(r"-?\d+(?:\.\d+)?", value.replace(",", ""))
        if match:
            return float(match.group())
    return None


def _normalize_dimensions(source: dict[str, Any] | None) -> dict[str, float | None]:
    source = source or {}
    dimensions = source.get("dimensions") if isinstance(source.get("dimensions"), dict) else source
    aliases = {
        "width_mm": ["width_mm", "width", "w", "폭", "가로"],
        "depth_mm": ["depth_mm", "depth", "d", "깊이", "세로"],
        "height_mm": ["height_mm", "height", "h", "높이"],
        "length_mm": ["length_mm", "length", "l", "길이"],
    }
    result: dict[str, float | None] = {}
    for target, keys in aliases.items():
        value = None
        for key in keys:
            if key in dimensions:
                value = _first_number(dimensions[key])
                if value is not None:
                    break
        result[target] = value
    return result


def _extract_prompt_dimensions(prompt: str) -> dict[str, float | None]:
    """Extract deterministic labelled dimensions when an LLM omits them."""
    aliases = {
        "width_mm": r"(?:폭|가로|width|wide)",
        "depth_mm": r"(?:깊이|세로|depth|deep)",
        "height_mm": r"(?:높이|height|high)",
        "length_mm": r"(?:길이|length|long)",
    }
    result: dict[str, float | None] = {key: None for key in aliases}
    for key, label in aliases.items():
        match = re.search(
            rf"{label}\s*(?:은|는|을|를|:|=)?\s*([0-9][0-9,]*(?:\.[0-9]+)?)\s*(mm|cm|m|밀리미터|센티미터|미터)?",
            prompt,
            re.IGNORECASE,
        )
        if not match:
            continue
        value = float(match.group(1).replace(",", ""))
        unit = (match.group(2) or "mm").lower()
        multiplier = 1000.0 if unit in {"m", "미터"} else 10.0 if unit in {"cm", "센티미터"} else 1.0
        result[key] = value * multiplier
    return result


def _normalize_components(source: dict[str, Any] | None, category: str) -> list[dict[str, Any]]:
    source = source or {}
    raw = source.get("main_components") or source.get("components") or []
    if isinstance(raw, str):
        raw = [item.strip() for item in re.split(r"[,/\n]", raw) if item.strip()]
    result: list[dict[str, Any]] = []
    for index, item in enumerate(raw):
        if isinstance(item, dict):
            name = str(item.get("name") or item.get("id") or f"component_{index+1}").strip()
            component = dict(item)
            component.setdefault("id", _slug(name, f"component_{index+1}"))
            component.setdefault("name", name)
        else:
            name = str(item).strip()
            component = {"id": _slug(name, f"component_{index+1}"), "name": name}
        component.setdefault("required", True)
        component.setdefault("quantity", 1)
        component.setdefault("source", "analysis")
        result.append(component)
    if not result:
        result = [
            {"id": value, "name": value.replace("_", " "), "required": True, "quantity": 1, "source": "default"}
            for value in DEFAULT_COMPONENTS[category]
        ]
    return result


def _slug(value: str, fallback: str) -> str:
    token = re.sub(r"[^A-Za-z0-9가-힣]+", "_", value).strip("_")
    return token[:64] or fallback


def _extract_visual(prompt: str, source: dict[str, Any] | None) -> dict[str, Any]:
    source = source or {}
    visual = dict(source.get("visual") or {})
    lower = prompt.lower()
    colors: list[str] = []
    for key, normalized in COLOR_ALIASES.items():
        if key.lower() in lower and normalized not in colors:
            colors.append(normalized)
    if colors:
        visual.setdefault("main_color", colors[0])
        if len(colors) > 1:
            visual.setdefault("secondary_color", colors[1])
    visual.setdefault("main_color", "industrial_gray")
    visual.setdefault("secondary_color", "dark_gray")
    if any(word in lower for word in ["스테인리스", "stainless"]):
        visual.setdefault("metal_finish", "stainless_steel")
    elif any(word in lower for word in ["알루미늄", "aluminum", "aluminium"]):
        visual.setdefault("metal_finish", "brushed_aluminum")
    else:
        visual.setdefault("metal_finish", "painted_steel")
    return visual


def build_design_state(
    *,
    project_id: str,
    revision: int,
    prompt: str,
    category: str,
    selected_2d_id: str,
    source_analysis: dict[str, Any] | None = None,
    meeting_analysis: dict[str, Any] | None = None,
    previous_design_state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    for source in (source_analysis or {}, meeting_analysis or {}):
        for key, value in source.items():
            if value not in (None, "", [], {}):
                merged[key] = value

    dimensions = _normalize_dimensions(merged)
    prompt_dimensions = _extract_prompt_dimensions(prompt)
    for key, value in prompt_dimensions.items():
        if dimensions.get(key) is None and value is not None:
            dimensions[key] = value
    components = _normalize_components(merged, category)
    purpose = str(
        merged.get("functional_purpose")
        or merged.get("purpose")
        or merged.get("summary")
        or prompt
    ).strip()
    operation = str(merged.get("operating_principle") or merged.get("operation") or "").strip()
    visual = _extract_visual(prompt, merged)
    safety = merged.get("safety_features") or merged.get("safety_requirements") or []
    unresolved = merged.get("uncertainties") or merged.get("unresolved_items") or []
    if isinstance(safety, str):
        safety = [safety]
    if isinstance(unresolved, str):
        unresolved = [unresolved]

    state = {
        "schema_version": "2.0",
        "design_id": (previous_design_state or {}).get("design_id") or f"DESIGN-{project_id}",
        "project_id": project_id,
        "revision": revision,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "units": "mm",
        "coordinate_system": {"up_axis": "Z", "front_axis": "-Y", "handedness": "right"},
        "selected_2d_id": selected_2d_id,
        "category": category,
        "purpose": purpose,
        "operating_principle": operation,
        "dimensions": dimensions,
        "components": components,
        "visual": visual,
        "safety_requirements": list(safety),
        "unresolved_items": list(unresolved),
        "source_prompt": prompt,
        "prompt_hash": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
        "consistency_contract": {
            "required_exact": [
                "purpose", "operating_principle", "components", "dimensions", "component_layout", "selected_2d_id"
            ],
            "required_high_similarity": ["overall_proportion", "silhouette", "main_color", "material_direction"],
            "allowed_variation": ["micro_surface", "small_fillet", "fine_texture", "decorative_detail"],
            "priority": [
                "functional_match", "component_match", "dimension_and_layout_match", "silhouette_match", "detail_appearance_match"
            ],
        },
        "validation_grade": "concept",
        "validation_scope": ["concept_review"],
    }
    return state
