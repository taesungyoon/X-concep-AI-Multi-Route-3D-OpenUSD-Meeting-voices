from __future__ import annotations

import json
import re
from typing import Any


def _token(value: Any) -> str:
    return re.sub(r"[^a-z0-9가-힣]+", "_", str(value or "").strip().lower()).strip("_")


def extract_json_object(text: str) -> dict[str, Any]:
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("model output does not contain a JSON object")
    value = json.loads(text[start : end + 1])
    if not isinstance(value, dict):
        raise ValueError("model output JSON is not an object")
    return value


def build_verification_prompt(requirements: list[dict[str, Any]]) -> str:
    normalized = []
    for item in requirements:
        if not isinstance(item, dict):
            continue
        row = {
            "class": str(item.get("class") or item.get("name") or "").strip(),
            "required_count": max(1, int(item.get("count") or 1)),
        }
        if isinstance(item.get("position"), (list, tuple)) and len(item["position"]) >= 2:
            row["position"] = [str(item["position"][0]), int(item["position"][1])]
        normalized.append(row)
    schema = {
        "objects": [{"class": "one of the requested classes", "count": 0}],
        "relationships": [{"subject": "class", "relation": "above", "object": "class", "passed": True}],
        "extra_major_objects": [],
        "occluded_or_uncertain": [],
    }
    return (
        "Inspect this single industrial concept image. Count only clearly visible physical instances. "
        "Do not infer hidden duplicates. Evaluate only the requested classes and relations. "
        "Return exactly one JSON object without markdown.\n"
        f"Requested contract: {json.dumps(normalized, ensure_ascii=False)}\n"
        f"Output schema: {json.dumps(schema, ensure_ascii=False)}"
    )


def evaluate_verification(
    requirements: list[dict[str, Any]],
    detected: dict[str, Any],
) -> dict[str, Any]:
    detected_counts: dict[str, int] = {}
    for item in detected.get("objects") or []:
        if not isinstance(item, dict):
            continue
        key = _token(item.get("class") or item.get("name"))
        if not key:
            continue
        try:
            detected_counts[key] = max(0, int(item.get("count") or 0))
        except (TypeError, ValueError):
            detected_counts[key] = 0

    checks: list[dict[str, Any]] = []
    required_classes: list[str] = []
    for item in requirements:
        if not isinstance(item, dict):
            continue
        name = str(item.get("class") or item.get("name") or "").strip()
        key = _token(name)
        if not key:
            continue
        required = max(1, int(item.get("count") or 1))
        observed = detected_counts.get(key, 0)
        required_classes.append(key)
        checks.append({
            "id": f"count:{key}",
            "class": name,
            "required": required,
            "observed": observed,
            "passed": observed == required,
        })

    relation_results = detected.get("relationships") or []
    for index, item in enumerate(requirements):
        position = item.get("position") if isinstance(item, dict) else None
        if not isinstance(position, (list, tuple)) or len(position) < 2:
            continue
        try:
            target_index = int(position[1])
            target = requirements[target_index]
        except (TypeError, ValueError, IndexError):
            continue
        subject_key = _token(item.get("class") or item.get("name"))
        target_key = _token(target.get("class") or target.get("name"))
        relation_key = _token(position[0])
        matched = any(
            isinstance(row, dict)
            and _token(row.get("subject")) == subject_key
            and _token(row.get("object")) == target_key
            and _token(row.get("relation")) == relation_key
            and row.get("passed") is True
            for row in relation_results
        )
        checks.append({
            "id": f"relation:{subject_key}:{relation_key}:{target_key}",
            "subject": subject_key,
            "relation": relation_key,
            "object": target_key,
            "passed": matched,
        })

    extras = [str(value) for value in (detected.get("extra_major_objects") or []) if str(value).strip()]
    if extras:
        checks.append({"id": "extra_major_objects", "observed": extras, "passed": False})
    uncertain = [str(value) for value in (detected.get("occluded_or_uncertain") or []) if str(value).strip()]
    if uncertain:
        checks.append({"id": "occluded_or_uncertain", "observed": uncertain, "passed": False})
    reasons = [row["id"] for row in checks if not row["passed"]]
    return {
        "passed": bool(checks) and not reasons,
        "checks": checks,
        "reasons": reasons,
        "detected": detected,
    }
