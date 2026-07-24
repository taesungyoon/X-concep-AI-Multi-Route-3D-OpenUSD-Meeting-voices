import json
from pathlib import Path

from PIL import Image

from xconcep_cad_vlm.dataset import load_records, validate_dataset
from xconcep_cad_vlm.preprocess import preprocess_dataset


def test_preprocess_generates_valid_dataset_and_keeps_duplicate_inputs_in_one_split(tmp_path: Path):
    source = tmp_path / "raw"
    source.mkdir()
    image = source / "shared.png"
    Image.new("RGB", (48, 32), "steelblue").save(image)
    records = [
        {
            "id": "part-001",
            "category": "part",
            "prompt": "폭 240mm 깊이 160mm 높이 120mm 센서 브래킷",
            "images": [{"path": "shared.png", "view": "front"}],
            "provenance": {
                "license": "LicenseRef-Xconcep-Internal-Generated",
                "training_allowed": True,
                "source_kind": "internal_test",
                "source_id": "part-001",
                "generator_version": "test",
            },
        },
        {
            "id": "part-002",
            "category": "part",
            "prompt": "폭 240mm 깊이 160mm 높이 120mm 센서 브래킷",
            "images": [{"path": "shared.png", "view": "front"}],
            "provenance": {
                "license": "LicenseRef-Xconcep-Internal-Generated",
                "training_allowed": True,
                "source_kind": "internal_test",
                "source_id": "part-002",
                "generator_version": "test",
            },
        },
    ]
    raw_manifest = source / "raw.jsonl"
    raw_manifest.write_text("".join(json.dumps(item, ensure_ascii=False) + "\n" for item in records), encoding="utf-8")

    output = tmp_path / "prepared"
    report = preprocess_dataset(raw_manifest, output, max_image_side=256)
    prepared = load_records(output)

    assert report["validation"]["valid"] is True
    assert validate_dataset(output)["record_count"] == 2
    assert {item["split"] for item in prepared} <= {"train", "eval", "test"}
    assert len({item["split"] for item in prepared}) == 1
    assert all((output / item["images"][0]).is_file() for item in prepared)
