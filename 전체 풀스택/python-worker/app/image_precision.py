from __future__ import annotations

import re
from typing import Any, Iterable


PRECISION_STRATA = {"counting", "position", "two_object", "color_attr"}
_SPATIAL_PATTERN = re.compile(
    r"\b(left of|right of|above|below|over|under|next to|beside|in front of|behind)\b",
    re.IGNORECASE,
)
_COUNT_PATTERN = re.compile(
    r"\b(two|three|four|five|six|seven|eight|nine|ten|2|3|4|5|6|7|8|9|10)\b",
    re.IGNORECASE,
)


def requirements_from_design_spec(design_spec: dict[str, Any]) -> tuple[str, list[dict[str, Any]]]:
    """Convert the deterministic DesignSpec into the image verifier contract.

    This keeps the 2D generator, semantic verifier and parametric 3D generator
    on the same component quantities and spatial relations.
    """
    requirements: list[dict[str, Any]] = []
    index_by_kind: dict[str, int] = {}
    for component in design_spec.get("components") or []:
        if not isinstance(component, dict) or component.get("required") is False:
            continue
        kind = str(component.get("kind") or component.get("id") or component.get("name") or "").strip()
        if not kind:
            continue
        try:
            count = max(1, int(component.get("quantity") or component.get("count") or 1))
        except (TypeError, ValueError):
            count = 1
        index_by_kind.setdefault(kind, len(requirements))
        requirements.append({"class": kind, "count": count})

    has_position = False
    relation_aliases = {
        "left_of": "left of",
        "right_of": "right of",
        "front_of": "in front of",
        "behind": "behind",
        "above": "above",
        "below": "below",
    }
    for relation in design_spec.get("relationships") or []:
        if not isinstance(relation, dict) or relation.get("required") is False:
            continue
        subject = str(relation.get("subject") or "").strip()
        target = str(relation.get("object") or "").strip()
        subject_index = index_by_kind.get(subject)
        target_index = index_by_kind.get(target)
        if subject_index is None or target_index is None or "position" in requirements[subject_index]:
            continue
        normalized_relation = relation_aliases.get(
            str(relation.get("relation") or "").strip().lower(),
            str(relation.get("relation") or "").strip().replace("_", " "),
        )
        if not normalized_relation:
            continue
        requirements[subject_index]["position"] = [normalized_relation, target_index]
        has_position = True

    if has_position:
        stratum = "position"
    elif len(requirements) > 1 or any(int(item["count"]) > 1 for item in requirements):
        stratum = "counting"
    else:
        stratum = "single_object"
    return stratum, requirements


def requires_precision_route(
    prompt: str,
    *,
    stratum: str | None = None,
    requirements: Iterable[dict[str, Any]] | None = None,
) -> bool:
    if str(stratum or "").strip().lower() in PRECISION_STRATA:
        return True
    normalized = list(requirements or [])
    if len(normalized) > 1 or any(int(item.get("count", 1) or 1) > 1 for item in normalized):
        return True
    return bool(_SPATIAL_PATTERN.search(prompt) or _COUNT_PATTERN.search(prompt))


def _object_phrase(item: dict[str, Any]) -> str:
    name = str(item.get("class") or item.get("name") or "object").strip()
    color = str(item.get("color") or "").strip()
    count = max(1, int(item.get("count", 1) or 1))
    descriptor = f"{color} {name}".strip()
    return f"{count}× {descriptor}"


def _position_instructions(requirements: list[dict[str, Any]]) -> list[str]:
    instructions: list[str] = []
    for index, item in enumerate(requirements):
        position = item.get("position")
        if not isinstance(position, (list, tuple)) or len(position) < 2:
            continue
        relation = str(position[0]).strip().upper()
        try:
            reference_index = int(position[1])
        except (TypeError, ValueError):
            continue
        if not 0 <= reference_index < len(requirements):
            continue
        subject = str(item.get("class") or item.get("name") or f"object {index + 1}").strip()
        reference = str(
            requirements[reference_index].get("class")
            or requirements[reference_index].get("name")
            or f"object {reference_index + 1}"
        ).strip()
        instructions.append(f"Place the {subject} clearly {relation} the {reference}; their centers must preserve that relation.")
    return instructions


def build_precision_prompt(
    prompt: str,
    *,
    stratum: str | None = None,
    requirements: Iterable[dict[str, Any]] | None = None,
) -> str:
    """Create an exact, renderer-friendly composition contract without case-specific exceptions."""
    items = [dict(item) for item in (requirements or []) if isinstance(item, dict)]
    lines = [
        "Create a clean professional studio photograph that obeys this exact scene contract.",
        f"Original request: {prompt.strip()}",
    ]
    if items:
        lines.append("Required visible objects (exact quantities, no duplicates):")
        lines.extend(f"- {_object_phrase(item)}; fully visible and visually separate." for item in items)
        total = sum(max(1, int(item.get("count", 1) or 1)) for item in items)
        lines.append(f"The final image must contain exactly {total} required object instances in total.")
        lines.extend(_position_instructions(items))

    normalized_stratum = str(stratum or "").strip().lower()
    if normalized_stratum == "counting":
        lines.append("Arrange repeated objects in one straight, evenly spaced row so every instance can be counted independently.")
    elif normalized_stratum in {"two_object", "color_attr"}:
        lines.append("Use a left/right product-layout with wide empty space between the two subjects; do not overlap them.")
    elif normalized_stratum == "position":
        lines.append("Use a strict diagram-like spatial layout with wide separation; do not swap the named subjects.")

    lines.extend([
        "Show every required object at large scale, uncropped, with an unobstructed silhouette.",
        "Use a plain neutral background and one consistent camera view.",
        "Do not add extra objects, people, reflections, mirrors, photographs, labels, letters, numbers, logos, or text.",
        "Do not merge, overlap, repeat, crop, or partially hide any required object.",
    ])
    return "\n".join(lines)


def route_prompt(
    prompt: str,
    *,
    stratum: str | None = None,
    requirements: Iterable[dict[str, Any]] | None = None,
) -> tuple[str, str]:
    if not requires_precision_route(prompt, stratum=stratum, requirements=requirements):
        return "fast", prompt.strip()
    return "precision", build_precision_prompt(
        prompt,
        stratum=stratum,
        requirements=requirements,
    )


def choose_verified_route(*, raw_passed: bool, precision_passed: bool) -> tuple[str, str]:
    """Deterministic production policy: prefer precision, then verified same-seed raw fallback."""
    if precision_passed:
        return "precision", "precision_verified"
    if raw_passed:
        return "raw", "precision_failed_raw_verified"
    return "precision", "both_failed_precision_retained"
