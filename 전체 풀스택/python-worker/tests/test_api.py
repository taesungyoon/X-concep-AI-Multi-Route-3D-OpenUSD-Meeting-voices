import os
from pathlib import Path

os.environ["STORAGE_PATH"] = str(Path(__file__).parent / "tmp_storage")
os.environ["PIPELINE_MODE"] = "mock"
os.environ["LLM_MODE"] = "mock"
os.environ["OPENAI_IMAGE_MODE"] = "mock"
os.environ["SHAPE_MODE"] = "mock"
os.environ["SPEECH_MODE"] = "mock"
os.environ["OPENSCAD_MODE"] = "mock"
os.environ["OPENSCAD_BIN"] = "__test_missing_openscad__"
os.environ["BLENDER_MODE"] = "mock"
os.environ["BLENDER_BIN"] = "__test_missing_blender__"

from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["execution_profile"] == "mock"
    assert response.json()["runtime_ready"] is False


def test_full_generation_flow():
    payload = {
        "project_id": "PRJ-TEST001",
        "prompt": "서보모터와 안전커버를 적용한 소형 자동화 검사 설비",
        "category": "equipment",
        "image_paths": [],
    }
    response = client.post("/v1/generate/2d", json=payload)
    assert response.status_code == 200
    results = response.json()["results"]
    assert len(results) == 4
    for item in results:
        assert Path(item["absolute_path"]).is_file()

    response = client.post("/v1/generate/3d", json={
        **payload,
        "selected_2d_id": results[0]["id"],
        "selected_image_path": results[0]["absolute_path"],
    })
    assert response.status_code == 200
    output = response.json()
    assert Path(output["absolute_paths"]["glb"]).is_file()
    assert Path(output["absolute_paths"]["stl"]).is_file()
    assert Path(output["absolute_paths"]["preview"]).is_file()

def test_http_probe_rejects_404_and_sends_bearer(monkeypatch):
    seen = {}
    class Response:
        is_success = False
    class Client:
        def __init__(self, **_kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *_args): pass
        def get(self, url, headers):
            seen.update(url=url, headers=headers)
            return Response()
    monkeypatch.setattr("app.pipeline.httpx.Client", Client)
    from app.pipeline import GenerationPipeline
    assert GenerationPipeline._probe_http("https://shape.test", "/health", "secret") is False
    assert seen == {"url": "https://shape.test/health", "headers": {"Authorization": "Bearer secret"}}
