from pathlib import Path

import pytest

from xconcep_cad_vlm.config import ConfigError, load_config

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("name", [
    "qwen3-vl-4b-qlora.json",
    "qwen3-vl-8b-qlora.json",
    "qwen3-vl-8b-h100-lora.json",
])
def test_profiles_are_valid(name):
    config = load_config(ROOT / "configs" / name)
    assert config.data["target_type"] == "design_spec"
    assert config.effective_batch_size >= 16
    assert config.output_dir.is_absolute()


def test_invalid_precision_is_rejected(tmp_path):
    source = load_config(ROOT / "configs" / "qwen3-vl-4b-qlora.json").raw
    source["training"]["fp16"] = True
    path = tmp_path / "invalid.json"
    import json
    path.write_text(json.dumps(source), encoding="utf-8")
    with pytest.raises(ConfigError):
        load_config(path)

