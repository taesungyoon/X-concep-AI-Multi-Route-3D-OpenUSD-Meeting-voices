from __future__ import annotations

import base64
import io

from fastapi.testclient import TestClient
from PIL import Image

import main


client = TestClient(main.app)


def _image_base64() -> str:
    buffer = io.BytesIO()
    Image.new("RGB", (8, 8), "white").save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode("ascii")


def test_health_does_not_eagerly_load_model():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["engine"] == "triposr"


def test_generate_returns_binary_glb(monkeypatch):
    monkeypatch.setattr(main.engine, "generate", lambda *args, **kwargs: b"glTFmock")
    response = client.post("/generate", json={"image": _image_base64()})
    assert response.status_code == 200
    assert response.headers["content-type"] == "model/gltf-binary"
    assert response.content == b"glTFmock"


def test_generate_rejects_invalid_image():
    response = client.post(
        "/generate", json={"image": base64.b64encode(b"not-an-image").decode("ascii")}
    )
    assert response.status_code == 400
