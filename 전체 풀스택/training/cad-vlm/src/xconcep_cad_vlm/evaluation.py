from __future__ import annotations

import math
from collections import defaultdict
from typing import Any


EVALUATION_SCHEMA = "xconcep.cad-vlm-evaluation/1.0"


def _quantity_map(items: Any, quantity_key: str) -> dict[str, int]:
    result: dict[str, int] = {}
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, dict):
            continue
        key = str(item.get("kind") or item.get("id") or "").strip()
        if not key:
            continue
        try:
            quantity = max(1, int(item.get(quantity_key) or 1))
        except (TypeError, ValueError):
            quantity = 1
        result[key] = result.get(key, 0) + quantity
    return result


def _relation_set(items: Any) -> set[tuple[str, str, str]]:
    return {
        (str(item.get("subject")), str(item.get("relation")), str(item.get("object")))
        for item in items if isinstance(items, list) and isinstance(item, dict)
    }


def _recall(required: dict[str, int], predicted: dict[str, int]) -> float:
    total = sum(required.values())
    return sum(min(count, predicted.get(key, 0)) for key, count in required.items()) / total if total else 1.0


def _precision(required: dict[str, int], predicted: dict[str, int]) -> float:
    total = sum(predicted.values())
    return sum(min(count, required.get(key, 0)) for key, count in predicted.items()) / total if total else float(not required)


def _wilson_lower(successes: int, total: int, z: float = 1.959963984540054) -> float:
    if total <= 0:
        return 0.0
    rate = successes / total
    denominator = 1.0 + z * z / total
    centre = rate + z * z / (2.0 * total)
    margin = z * math.sqrt(rate * (1.0 - rate) / total + z * z / (4.0 * total * total))
    return max(0.0, (centre - margin) / denominator)


def evaluate_prediction(
    record: dict[str, Any],
    prediction: dict[str, Any] | None,
    *,
    dimension_tolerance_pct: float = 5.0,
) -> dict[str, Any]:
    truth = record.get("design_spec") or {}
    valid_json = isinstance(prediction, dict)
    predicted = prediction if valid_json else {}
    schema_passed = bool(
        valid_json
        and predicted.get("category") == truth.get("category")
        and predicted.get("units") == "mm"
    )

    truth_components = _quantity_map(truth.get("components"), "quantity")
    predicted_components = _quantity_map(predicted.get("components"), "quantity")
    component_recall = _recall(truth_components, predicted_components)
    component_precision = _precision(truth_components, predicted_components)
    component_quantities_passed = all(predicted_components.get(key) == value for key, value in truth_components.items())

    truth_features = _quantity_map(truth.get("features"), "count")
    predicted_features = _quantity_map(predicted.get("features"), "count")
    feature_recall = _recall(truth_features, predicted_features)
    feature_quantities_passed = all(predicted_features.get(key) == value for key, value in truth_features.items())

    dimension_rows: list[dict[str, Any]] = []
    for key, expected in (truth.get("dimensions") or {}).items():
        if expected is None:
            continue
        actual = (predicted.get("dimensions") or {}).get(key)
        try:
            expected_value = float(expected)
            actual_value = float(actual)
            error_pct = abs(actual_value - expected_value) / max(abs(expected_value), 1e-9) * 100.0
            passed = error_pct <= dimension_tolerance_pct
        except (TypeError, ValueError):
            actual_value, error_pct, passed = actual, None, False
        dimension_rows.append({
            "field": key,
            "expected": expected,
            "actual": actual_value,
            "error_pct": round(error_pct, 4) if error_pct is not None else None,
            "passed": passed,
        })
    dimensions_passed = bool(dimension_rows) and all(row["passed"] for row in dimension_rows)
    dimension_score = (
        sum(
            max(
                0.0,
                1.0 - min(float(row["error_pct"] if row["error_pct"] is not None else 100.0), 100.0) / 100.0,
            )
            for row in dimension_rows
        )
        / len(dimension_rows)
        if dimension_rows else 0.0
    )

    truth_relations = _relation_set(truth.get("relationships"))
    predicted_relations = _relation_set(predicted.get("relationships"))
    relationship_recall = len(truth_relations & predicted_relations) / len(truth_relations) if truth_relations else 1.0
    relationships_passed = relationship_recall == 1.0

    passed = bool(
        schema_passed
        and component_recall == 1.0
        and component_quantities_passed
        and feature_recall == 1.0
        and feature_quantities_passed
        and dimensions_passed
        and relationships_passed
    )
    score = (
        float(schema_passed) * 0.10
        + component_recall * 0.25
        + feature_recall * 0.20
        + dimension_score * 0.25
        + relationship_recall * 0.10
        + component_precision * 0.10
    )
    return {
        "id": record.get("id"),
        "category": record.get("category"),
        "passed": passed,
        "score": round(score, 4),
        "checks": {
            "valid_json": valid_json,
            "schema_and_category": schema_passed,
            "component_recall": round(component_recall, 4),
            "component_precision": round(component_precision, 4),
            "component_quantities": component_quantities_passed,
            "feature_recall": round(feature_recall, 4),
            "feature_quantities": feature_quantities_passed,
            "dimensions": dimensions_passed,
            "relationship_recall": round(relationship_recall, 4),
        },
        "dimension_rows": dimension_rows,
    }


def evaluate_predictions(
    records: list[dict[str, Any]],
    predictions: dict[str, dict[str, Any] | None],
    *,
    dimension_tolerance_pct: float = 5.0,
    target: float = 0.95,
    min_cases_per_category: int = 200,
) -> dict[str, Any]:
    cases = [
        evaluate_prediction(
            record,
            predictions.get(str(record.get("id"))),
            dimension_tolerance_pct=dimension_tolerance_pct,
        )
        for record in records
    ]
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for case in cases:
        grouped[str(case.get("category") or "unknown")].append(case)
    categories: dict[str, Any] = {}
    for category, rows in sorted(grouped.items()):
        successes = sum(bool(row["passed"]) for row in rows)
        lower = _wilson_lower(successes, len(rows))
        categories[category] = {
            "successes": successes,
            "total": len(rows),
            "observed_rate": round(successes / len(rows), 4),
            "wilson_95_lower": round(lower, 4),
            "passed": len(rows) >= min_cases_per_category and lower >= target,
        }
    successes = sum(bool(case["passed"]) for case in cases)
    return {
        "schema": EVALUATION_SCHEMA,
        "target": target,
        "dimension_tolerance_pct": dimension_tolerance_pct,
        "min_cases_per_category": min_cases_per_category,
        "summary": {
            "successes": successes,
            "total": len(cases),
            "observed_rate": round(successes / len(cases), 4) if cases else 0.0,
            "mean_score": round(sum(float(case["score"]) for case in cases) / len(cases), 4) if cases else 0.0,
        },
        "categories": categories,
        "target_achieved": bool(categories) and all(row["passed"] for row in categories.values()),
        "cases": cases,
    }
