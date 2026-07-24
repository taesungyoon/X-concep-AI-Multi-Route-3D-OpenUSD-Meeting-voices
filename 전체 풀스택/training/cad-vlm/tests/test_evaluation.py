from __future__ import annotations

import copy
import json
import shutil
from pathlib import Path

import pytest

from xconcep_cad_vlm.dataset import DatasetValidationError, load_records, validate_dataset
from xconcep_cad_vlm.evaluation import evaluate_prediction, evaluate_predictions


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "examples"


def test_gold_design_spec_passes_all_semantic_checks():
    record = next(item for item in load_records(DATA) if item["split"] == "eval")
    case = evaluate_prediction(record, copy.deepcopy(record["design_spec"]))

    assert case["passed"] is True
    assert case["score"] == 1.0
    assert all(row["passed"] for row in case["dimension_rows"])


def test_wrong_quantity_and_dimension_fail_even_with_valid_json():
    record = next(item for item in load_records(DATA) if item["split"] == "eval")
    prediction = copy.deepcopy(record["design_spec"])
    prediction["components"][0]["quantity"] = 99
    prediction["dimensions"]["width_mm"] = float(record["design_spec"]["dimensions"]["width_mm"]) * 2

    case = evaluate_prediction(record, prediction)

    assert case["passed"] is False
    assert case["checks"]["component_quantities"] is False
    assert case["checks"]["dimensions"] is False


def test_small_perfect_sample_does_not_claim_95_percent_target():
    records = [item for item in load_records(DATA) if item["split"] == "eval"]
    predictions = {item["id"]: item["design_spec"] for item in records}
    report = evaluate_predictions(records, predictions, min_cases_per_category=200)

    assert report["summary"]["observed_rate"] == 1.0
    assert report["target_achieved"] is False


def test_validator_rejects_image_hash_tampering(tmp_path):
    copied = tmp_path / "dataset"
    shutil.copytree(DATA, copied)
    records = [json.loads(line) for line in (copied / "records.jsonl").read_text(encoding="utf-8").splitlines()]
    view = next(iter(records[0]["image_sha256"]))
    records[0]["image_sha256"][view] = "0" * 64
    (copied / "records.jsonl").write_text(
        "".join(json.dumps(item, ensure_ascii=False, sort_keys=True) + "\n" for item in records),
        encoding="utf-8",
    )

    with pytest.raises(DatasetValidationError, match="image_sha256 mismatch"):
        validate_dataset(copied)
