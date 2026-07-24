from pathlib import Path

from xconcep_cad_vlm.dataset import load_records, make_training_example, validate_dataset

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "examples"


def test_generated_examples_validate():
    report = validate_dataset(DATA)
    assert report["record_count"] == 9
    assert report["category_counts"] == {"equipment": 3, "module": 3, "part": 3}
    assert report["split_counts"] == {"eval": 3, "train": 6}


def test_php_based_training_example_has_observed_preview_and_json_answer():
    record = load_records(DATA)[0]
    example = make_training_example(record, DATA, target_type="design_spec", max_images=3)
    assert len(example["images"]) == 1
    assert len([item for item in example["messages"][0]["content"] if item["type"] == "image"]) == 1
    assert record["cad_context"]["schema"] == "xconcep.php-cad-context/1.0"
    assert example["messages"][1]["content"][0]["text"].startswith("{")
