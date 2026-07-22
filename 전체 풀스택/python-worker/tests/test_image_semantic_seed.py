from dataclasses import replace

from PIL import Image
import io

from app.openai_image_client import GPTImageClient
from app.settings import get_settings


def _png_bytes() -> bytes:
    stream = io.BytesIO()
    Image.new("RGB", (64, 64), (80, 120, 160)).save(stream, format="PNG")
    return stream.getvalue()


def test_fallback_reuses_actual_precision_retry_seed(tmp_path, monkeypatch):
    settings = replace(
        get_settings(),
        storage_path=tmp_path,
        openai_image_mode="comfyui",
        image_concept_count=1,
        image_semantic_verifier_url="http://127.0.0.1:8191",
        comfyui_max_attempts=2,
    )
    client = GPTImageClient(settings)
    calls = []
    failed = {"passed": False, "checks": [{"id": "non_blank_channels", "passed": False}]}
    passed = {"passed": True, "checks": [{"id": "non_blank_channels", "passed": True}]}
    qualities = iter([failed, passed, passed])
    verdicts = iter([
        {"passed": False, "evaluator": "fixture", "reasons": ["missing object"]},
        {"passed": True, "evaluator": "fixture", "reasons": []},
    ])

    def generate(prompt, _reference, _project_id, _index, noise_seed=None):
        calls.append((prompt, noise_seed))
        return _png_bytes()

    monkeypatch.setattr("app.openai_image_client.validate_generated_image", lambda *_a, **_k: next(qualities))
    monkeypatch.setattr("app.openai_image_client.secrets.randbits", lambda _bits: 1000)
    monkeypatch.setattr(client, "_call_comfyui", generate)
    monkeypatch.setattr(client, "_verify_semantics", lambda *_args: next(verdicts))
    analysis = {
        "image_task": "counting",
        "image_requirements": [{"class": "motor", "count": 2}],
        "concept_variants": [{"name": "fallback", "image_prompt": "two motors"}],
    }

    result = client.generate_concepts("PRJ-RETRY-SEED", "배치", "equipment", [], analysis)[0]

    verification = result["semantic_verification"]
    assert result["route"] == "raw"
    assert [call[1] for call in calls] == [1000, 1001, 1001]
    assert verification["requested_noise_seed"] == 1000
    assert verification["shared_noise_seed"] == 1001
    assert verification["precision_noise_seed"] == verification["raw_noise_seed"] == 1001
