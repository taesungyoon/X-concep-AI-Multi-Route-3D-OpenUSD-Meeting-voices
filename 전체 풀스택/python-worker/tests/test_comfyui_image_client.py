from __future__ import annotations

from dataclasses import replace
from io import BytesIO
import json

from PIL import Image

from app.openai_image_client import GPTImageClient
from app.settings import get_settings


def _png_bytes() -> bytes:
    output = BytesIO()
    Image.new("RGB", (32, 32), "navy").save(output, "PNG")
    return output.getvalue()


def test_comfyui_is_local_default(monkeypatch):
    monkeypatch.delenv("OPENAI_IMAGE_MODE", raising=False)
    assert get_settings().openai_image_mode == "comfyui"


def test_comfyui_generates_four_verified_concepts(tmp_path, monkeypatch):
    settings = replace(
        get_settings(),
        storage_path=tmp_path,
        openai_image_mode="comfyui",
        image_min_width=32,
        image_min_height=32,
        image_min_file_bytes=1,
        image_min_channel_stddev=0,
    )
    client = GPTImageClient(settings)
    calls = []
    monkeypatch.setattr(
        client,
        "_call_comfyui",
        lambda prompt, reference, project_id, index: calls.append((prompt, reference, project_id, index)) or _png_bytes(),
    )
    analysis = {
        "concept_variants": [
            {"name": f"대안 {index}", "image_prompt": f"industrial concept {index}"}
            for index in range(1, 5)
        ]
    }

    results = client.generate_concepts("PRJ-COMFY", "설비", "equipment", [], analysis)

    assert len(results) == 4
    assert [call[3] for call in calls] == [1, 2, 3, 4]
    assert all(Image.open(item["absolute_path"]).format == "PNG" for item in results)


def test_openai_is_an_optional_generation_mode(tmp_path, monkeypatch):
    settings = replace(
        get_settings(),
        storage_path=tmp_path,
        openai_image_mode="openai",
        openai_api_key="test-key",
        openai_image_usage_db=tmp_path / "usage.sqlite3",
        image_min_width=32,
        image_min_height=32,
        image_min_file_bytes=1,
        image_min_channel_stddev=0,
        image_require_expected_aspect=False,
    )
    client = GPTImageClient(settings)
    calls = []
    monkeypatch.setattr(
        client,
        "_call_api",
        lambda prompt, reference, project_id, index: calls.append((prompt, reference, project_id, index)) or _png_bytes(),
    )
    analysis = {
        "concept_variants": [
            {"name": f"OpenAI 대안 {index}", "image_prompt": f"industrial concept {index}"}
            for index in range(1, 5)
        ]
    }

    results = client.generate_concepts("PRJ-OPENAI", "설비", "equipment", [], analysis)

    assert len(results) == 4
    assert len(calls) == 4
    assert all(reference is None for _prompt, reference, _project_id, _index in calls)
    assert all(Image.open(item["absolute_path"]).format == "PNG" for item in results)


def test_flux2_workflow_supports_optional_reference(tmp_path):
    settings = replace(get_settings(), storage_path=tmp_path, openai_image_mode="comfyui")
    workflow = GPTImageClient(settings)._comfyui_flux_workflow(
        "industrial machine", "reference.png", "xconcep/test"
    )

    assert workflow["1"]["inputs"]["unet_name"] == settings.comfyui_unet_model
    assert workflow["10"]["inputs"]["positive"] == ["17", 0]
    assert workflow["10"]["inputs"]["negative"] == ["18", 0]
    assert workflow["13"]["class_type"] == "SaveImage"


def test_structured_multi_object_request_uses_precision_route(tmp_path, monkeypatch):
    settings = replace(
        get_settings(), storage_path=tmp_path, openai_image_mode="comfyui",
        image_concept_count=1, image_min_width=32, image_min_height=32,
        image_min_file_bytes=1, image_min_channel_stddev=0,
    )
    client = GPTImageClient(settings)
    prompts = []
    monkeypatch.setattr(
        client, "_call_comfyui",
        lambda prompt, *_args: prompts.append(prompt) or _png_bytes(),
    )
    analysis = {
        "image_task": "position",
        "image_requirements": [
            {"class": "motor", "count": 1},
            {"class": "sensor", "count": 1, "position": ["above", 0]},
        ],
        "concept_variants": [{"name": "정밀 배치", "image_prompt": "sensor above motor"}],
    }

    results = client.generate_concepts("PRJ-PRECISION", "배치", "equipment", [], analysis)

    assert results[0]["route"] == "precision"
    assert "exactly 2 required object instances" in prompts[0]
    assert "Generate one product only" not in prompts[0]
    manifest = json.loads((tmp_path / "projects" / "PRJ-PRECISION" / "concept_generation_manifest.json").read_text(encoding="utf-8"))
    assert manifest["concepts"][0]["route"] == "precision"


def test_semantic_verifier_uses_same_seed_raw_fallback(tmp_path, monkeypatch):
    settings = replace(
        get_settings(), storage_path=tmp_path, openai_image_mode="comfyui",
        image_concept_count=1, image_min_width=32, image_min_height=32,
        image_min_file_bytes=1, image_min_channel_stddev=0,
        image_semantic_verifier_url="http://127.0.0.1:8191",
    )
    client = GPTImageClient(settings)
    calls = []

    def fake_generate(prompt, _reference, _project_id, _index, noise_seed=None):
        calls.append((prompt, noise_seed))
        return _png_bytes()

    verdicts = iter([
        {"passed": False, "evaluator": "fixture", "reasons": ["missing object"]},
        {"passed": True, "evaluator": "fixture", "reasons": []},
    ])
    monkeypatch.setattr(client, "_call_comfyui", fake_generate)
    monkeypatch.setattr(client, "_verify_semantics", lambda *_args: next(verdicts))
    analysis = {
        "image_task": "position",
        "image_requirements": [
            {"class": "motor", "count": 1},
            {"class": "sensor", "count": 1, "position": ["above", 0]},
        ],
        "concept_variants": [{"name": "fallback", "image_prompt": "sensor above motor"}],
    }

    results = client.generate_concepts("PRJ-FALLBACK", "배치", "equipment", [], analysis)

    assert results[0]["requested_route"] == "precision"
    assert results[0]["route"] == "raw"
    assert results[0]["semantic_verification"]["selection_reason"] == "precision_failed_raw_verified"
    assert len(calls) == 2
    assert calls[0][1] == calls[1][1]
    assert calls[0][0] != calls[1][0]


def test_generated_image_quality_failure_is_not_persisted(tmp_path, monkeypatch):
    settings = replace(
        get_settings(),
        storage_path=tmp_path,
        openai_image_mode="comfyui",
        comfyui_max_attempts=1,
        image_min_width=1024,
        image_min_height=1024,
        image_min_file_bytes=1,
        image_min_channel_stddev=0,
    )
    client = GPTImageClient(settings)
    monkeypatch.setattr(client, "_call_comfyui", lambda *args: _png_bytes())
    analysis = {"concept_variants": [{"name": "invalid", "image_prompt": "invalid"}]}

    import pytest
    with pytest.raises(RuntimeError, match="minimum_dimensions"):
        client.generate_concepts("PRJ-QUALITY", "test prompt", "equipment", [], analysis)

    assert not (tmp_path / "projects" / "PRJ-QUALITY" / "concepts" / "concept-1.png").exists()
