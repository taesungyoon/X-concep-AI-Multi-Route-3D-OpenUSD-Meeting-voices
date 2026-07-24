from xconcep_cad_vlm.verification import (
    build_verification_prompt,
    evaluate_verification,
    extract_json_object,
)


REQUIREMENTS = [
    {"class": "conveyor", "count": 1},
    {"class": "servo_motor", "count": 3},
    {"class": "vision_camera", "count": 1, "position": ["above", 0]},
]


def test_exact_component_counts_and_relation_pass():
    result = evaluate_verification(REQUIREMENTS, {
        "objects": [
            {"class": "conveyor", "count": 1},
            {"class": "servo motor", "count": 3},
            {"class": "vision_camera", "count": 1},
        ],
        "relationships": [
            {"subject": "vision camera", "relation": "above", "object": "conveyor", "passed": True},
        ],
        "extra_major_objects": [],
        "occluded_or_uncertain": [],
    })
    assert result["passed"] is True


def test_duplicate_conveyor_is_rejected():
    result = evaluate_verification(REQUIREMENTS, {
        "objects": [
            {"class": "conveyor", "count": 3},
            {"class": "servo_motor", "count": 3},
            {"class": "vision_camera", "count": 1},
        ],
        "relationships": [],
        "extra_major_objects": [],
        "occluded_or_uncertain": [],
    })
    assert result["passed"] is False
    assert "count:conveyor" in result["reasons"]


def test_prompt_and_json_extraction_are_deterministic():
    prompt = build_verification_prompt(REQUIREMENTS)
    assert "required_count" in prompt
    assert "Return exactly one JSON object" in prompt
    assert extract_json_object('prefix {"objects": []} suffix') == {"objects": []}
