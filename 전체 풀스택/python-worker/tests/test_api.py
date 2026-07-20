import os
from pathlib import Path

os.environ["STORAGE_PATH"] = str(Path(__file__).parent / "tmp_storage")

from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


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
