from pathlib import Path

import trimesh
from PIL import Image, ImageDraw

from app.manufacturing_feedback import (
    evaluate_candidate,
    run_bounded_feedback_loop,
    score_holdout,
)


def _image(path: Path, box: tuple[int, int, int, int]) -> None:
    image = Image.new("RGB", (256, 256), "white")
    ImageDraw.Draw(image).rectangle(box, fill=(60, 80, 100))
    image.save(path)


def _contract() -> dict:
    return {
        "overall_dimensions_mm": {"width": 240, "depth": 160, "height": 120},
        "requirement_coverage": {
            "components": [{"id": "main_body", "required": 1, "represented": 1, "passed": True}],
            "features": [],
            "relationships": [],
        },
    }


def test_identical_reference_and_watertight_box_pass(tmp_path):
    reference = tmp_path / "reference.png"
    _image(reference, (32, 64, 224, 192))
    glb = tmp_path / "box.glb"
    trimesh.creation.box(extents=(0.24, 0.16, 0.12)).export(glb)

    report = evaluate_candidate(
        reference_path=reference,
        candidate_paths=[reference],
        glb_path=glb,
        contract=_contract(),
        target=0.95,
    )

    assert report["passed"] is True
    assert report["score"] >= 0.95
    assert report["manufacturing_approval"] is False
    assert report["appearance"]["independent"] is True
    assert report["manufacturing"]["contract_coverage_independent"] is False


def test_appearance_mismatch_is_not_hidden_by_manufacturing_score(tmp_path):
    reference = tmp_path / "reference.png"
    candidate = tmp_path / "candidate.png"
    _image(reference, (20, 90, 236, 166))
    _image(candidate, (90, 20, 166, 236))
    glb = tmp_path / "box.glb"
    trimesh.creation.box(extents=(0.24, 0.16, 0.12)).export(glb)

    report = evaluate_candidate(
        reference_path=reference,
        candidate_paths=[candidate],
        glb_path=glb,
        contract=_contract(),
        target=0.95,
    )

    assert report["passed"] is False
    assert report["score"] == min(report["silhouette_score"], report["manufacturing"]["score"])
    assert report["regeneration_plan"]["recommended"] is True
    assert report["regeneration_plan"]["preserve_best_candidate"] is True


def test_final_render_is_primary_and_alternate_projection_is_diagnostic(tmp_path):
    reference = tmp_path / "reference.png"
    final_render = tmp_path / "final.png"
    alternate_projection = tmp_path / "alternate.png"
    _image(reference, (32, 64, 224, 192))
    _image(final_render, (90, 20, 166, 236))
    _image(alternate_projection, (32, 64, 224, 192))
    glb = tmp_path / "box.glb"
    trimesh.creation.box(extents=(0.24, 0.16, 0.12)).export(glb)

    report = evaluate_candidate(
        reference_path=reference,
        candidate_paths=[final_render, alternate_projection],
        glb_path=glb,
        contract=_contract(),
        target=0.95,
    )

    appearance = report["appearance"]
    assert appearance["primary_candidate"]["path"] == str(final_render)
    assert appearance["best_candidate"]["path"] == str(alternate_projection)
    assert appearance["score"] < appearance["diagnostic_best_score"]
    assert report["score"] == report["silhouette_score"]
    assert report["passed"] is False


def test_missing_catalog_detail_fails_manufacturing_gate(tmp_path):
    reference = tmp_path / "reference.png"
    _image(reference, (32, 64, 224, 192))
    glb = tmp_path / "box.glb"
    trimesh.creation.box(extents=(0.24, 0.16, 0.12)).export(glb)
    contract = _contract()
    contract["requirement_coverage"]["assembly_details"] = [{
        "id": "control_panel:hmi_screen",
        "parent": "control_panel",
        "kind": "hmi_screen",
        "required": 1,
        "represented": 0,
        "passed": False,
    }]

    report = evaluate_candidate(
        reference_path=reference,
        candidate_paths=[reference],
        glb_path=glb,
        contract=contract,
        target=0.95,
    )

    checks = {item["id"]: item for item in report["manufacturing"]["checks"]}
    assert checks["assembly_detail_contract"]["passed"] is False
    assert "control_panel:hmi_screen" in report["manufacturing"]["failed_requirements"]
    assert report["passed"] is False


def test_bounded_loop_preserves_best_when_budget_exhausts():
    scores = [0.82, 0.61, 0.74]

    def factory(index, feedback, best):
        return {"index": index, "feedback": feedback, "previous_best": best["score"] if best else None}

    def evaluator(candidate):
        score = scores[candidate["index"] - 1]
        return {"score": score, "passed": False, "regeneration_plan": {"recommended": True}}

    result = run_bounded_feedback_loop(factory, evaluator, max_attempts=3)

    assert result["attempt_count"] == 3
    assert result["target_achieved"] is False
    assert result["best_attempt"]["attempt"] == 1
    assert result["stopped_reason"] == "attempt_budget_exhausted"


def test_holdout_requires_sample_size_and_wilson_lower_bound():
    report = score_holdout(
        [{"category": "part", "passed": True}],
        target=0.95,
        min_cases_per_category=200,
    )

    assert report["target_achieved"] is False
    assert report["categories"]["part"]["observed_rate"] == 1.0
    assert report["categories"]["part"]["passed"] is False
