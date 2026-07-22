from __future__ import annotations

import hashlib
import math
import re
from statistics import NormalDist, mean, variance
from typing import Any, Iterable, Mapping


_STEP_ENTITY = re.compile(r"#(?P<id>\d+)\s*=\s*(?P<type>[A-Z0-9_]+)\s*\(", re.IGNORECASE)
_STEP_DEFINITION = re.compile(r"#(\d+)\s*=", re.IGNORECASE)
_STEP_REFERENCE = re.compile(r"#(\d+)")


def step_pmi_semantics(text: str) -> dict[str, Any]:
    entities = [(match.group("id"), match.group("type").upper()) for match in _STEP_ENTITY.finditer(text)]
    entity_ids = set(_STEP_DEFINITION.findall(text))
    references = _STEP_REFERENCE.findall(text)
    unresolved = sorted({reference for reference in references if reference not in entity_ids}, key=int)
    types = [entity_type for _, entity_type in entities]
    families = {
        "dimension": sum("DIMENSION" in entity_type or entity_type in {"LENGTH_MEASURE_WITH_UNIT", "MEASURE_REPRESENTATION_ITEM"} for entity_type in types),
        "tolerance": sum("TOLERANCE" in entity_type for entity_type in types),
        "datum": sum("DATUM" in entity_type for entity_type in types),
        "annotation": sum("ANNOTATION" in entity_type or "DRAUGHTING" in entity_type for entity_type in types),
    }
    return {
        "entity_count": len(entity_ids),
        "reference_count": len(references),
        "unresolved_reference_count": len(unresolved),
        "unresolved_reference_sample": unresolved[:20],
        "families": families,
        "semantic_pmi_entity_count": sum(families.values()),
    }


def deterministic_split(identity: str, calibration_fraction: float = 0.2, salt: str = "xconcep-quality-v1") -> str:
    """Keep every seed/evaluator for one logical case in the same stable split."""
    if not 0.0 < calibration_fraction < 1.0:
        raise ValueError("calibration_fraction must be between 0 and 1")
    digest = hashlib.sha256(f"{salt}:{identity}".encode("utf-8")).digest()
    bucket = int.from_bytes(digest[:8], "big") / float(1 << 64)
    return "calibration" if bucket < calibration_fraction else "holdout"


def wilson_interval(successes: int, total: int, confidence: float = 0.95) -> tuple[float, float]:
    if total < 1:
        return 0.0, 0.0
    if successes < 0 or successes > total:
        raise ValueError("successes must be between zero and total")
    if not 0.0 < confidence < 1.0:
        raise ValueError("confidence must be between 0 and 1")
    z = NormalDist().inv_cdf(0.5 + confidence / 2.0)
    proportion = successes / total
    denominator = 1.0 + z * z / total
    centre = (proportion + z * z / (2.0 * total)) / denominator
    margin = z * math.sqrt(proportion * (1.0 - proportion) / total + z * z / (4.0 * total * total)) / denominator
    return max(0.0, centre - margin), min(1.0, centre + margin)


def binary_summary(values: Iterable[bool]) -> dict[str, Any]:
    samples = [bool(value) for value in values]
    passed = sum(samples)
    low, high = wilson_interval(passed, len(samples))
    return {
        "passed": passed,
        "total": len(samples),
        "score_pct": round(passed / len(samples) * 100.0, 4) if samples else 0.0,
        "wilson_95ci_pct": [round(low * 100.0, 4), round(high * 100.0, 4)],
    }


def score_distribution(scores: Iterable[float]) -> dict[str, Any]:
    samples = [float(score) for score in scores]
    if not samples:
        return {"count": 0, "mean_pct": 0.0, "min_pct": 0.0, "max_pct": 0.0, "variance": 0.0, "mean_95ci_pct": [0.0, 0.0]}
    average = mean(samples)
    sample_variance = variance(samples) if len(samples) > 1 else 0.0
    margin = NormalDist().inv_cdf(0.975) * math.sqrt(sample_variance / len(samples)) if len(samples) > 1 else 0.0
    return {
        "count": len(samples),
        "mean_pct": round(average, 4),
        "min_pct": round(min(samples), 4),
        "max_pct": round(max(samples), 4),
        "variance": round(sample_variance, 6),
        "mean_95ci_pct": [round(max(0.0, average - margin), 4), round(min(100.0, average + margin), 4)],
    }


def binary_agreement(left: Mapping[str, bool], right: Mapping[str, bool]) -> dict[str, Any]:
    shared = sorted(set(left) & set(right))
    if not shared:
        return {"shared_cases": 0, "agreement_pct": None, "cohen_kappa": None, "confusion": {}}
    both_true = sum(bool(left[key]) and bool(right[key]) for key in shared)
    left_true_right_false = sum(bool(left[key]) and not bool(right[key]) for key in shared)
    left_false_right_true = sum(not bool(left[key]) and bool(right[key]) for key in shared)
    both_false = len(shared) - both_true - left_true_right_false - left_false_right_true
    observed = (both_true + both_false) / len(shared)
    left_true_rate = (both_true + left_true_right_false) / len(shared)
    right_true_rate = (both_true + left_false_right_true) / len(shared)
    expected = left_true_rate * right_true_rate + (1.0 - left_true_rate) * (1.0 - right_true_rate)
    kappa = (observed - expected) / (1.0 - expected) if not math.isclose(expected, 1.0) else (1.0 if math.isclose(observed, 1.0) else 0.0)
    return {
        "shared_cases": len(shared),
        "agreement_pct": round(observed * 100.0, 4),
        "cohen_kappa": round(kappa, 6),
        "confusion": {
            "both_pass": both_true,
            "left_pass_right_fail": left_true_right_false,
            "left_fail_right_pass": left_false_right_true,
            "both_fail": both_false,
        },
    }
