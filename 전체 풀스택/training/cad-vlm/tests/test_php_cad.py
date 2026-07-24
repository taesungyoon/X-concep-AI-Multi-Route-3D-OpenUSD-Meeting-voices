import json
from pathlib import Path

from xconcep_cad_vlm.dataset import _instruction, load_records, validate_dataset
from xconcep_cad_vlm.php_cad import import_php_cad_packages
from xconcep_cad_vlm.preprocess import preprocess_dataset


def test_php_package_import_then_canonical_preprocess(tmp_path: Path):
    package = tmp_path / "CAD-TEST"
    (package / "geometry").mkdir(parents=True)
    (package / "quality").mkdir()
    (package / "metadata").mkdir()
    manifest = {"schema_version": "1.0", "sample_id": "CAD-TEST", "source": {"format": "dxf", "sha256": "a" * 64}, "label": {"category": "bracket", "description": "steel bracket"}, "split": "train", "provenance": {"version": "1.0.0"}}
    geometry = {"parser_mode": "php_ascii_dxf_v1", "entity_counts": {"LINE": 2}, "bbox": {"min": [0, 0, 0], "extent": [100, 50, 0]}, "primitives": [{"type": "line", "start": [0, 0, 0], "end": [100, 50, 0]}], "points": [], "topology": {}, "surfaces": {}}
    (package / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (package / "geometry" / "geometry.json").write_text(json.dumps(geometry), encoding="utf-8")
    (package / "quality" / "report.json").write_text(json.dumps({"score": 1.0}), encoding="utf-8")
    (package / "metadata" / "label.json").write_text(json.dumps({"category": "bracket", "description": "steel bracket"}), encoding="utf-8")
    raw = tmp_path / "raw"
    assert import_php_cad_packages(package, raw, license_id="LicenseRef-Xconcep-Internal-Generated", training_allowed=True)["imported_count"] == 1
    prepared = tmp_path / "prepared"
    preprocess_dataset(raw / "records.jsonl", prepared, max_image_side=256)
    record = load_records(prepared)[0]
    assert record["cad_context"]["parser_mode"] == "php_ascii_dxf_v1"
    assert "CAD preprocessing observations" in _instruction(record, "design_spec")
    assert validate_dataset(prepared)["record_count"] == 1
