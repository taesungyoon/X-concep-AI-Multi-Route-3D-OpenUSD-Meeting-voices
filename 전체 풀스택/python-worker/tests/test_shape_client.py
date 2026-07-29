from pathlib import Path

import httpx

from app.hunyuan_client import ShapeGenerationClient
from app.settings import get_settings


def test_hunyuan3d_mode_sends_bearer_key(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("SHAPE_MODE", "hunyuan3d")
    monkeypatch.setenv("SHAPE_PROVIDER", "hunyuan3d")
    monkeypatch.setenv("SHAPE_API_URL", "https://shape.example.test")
    monkeypatch.setenv("SHAPE_API_KEY", "secret")
    seen = {}

    class Client:
        def __init__(self, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def post(self, url, **kwargs):
            seen.update(url=url, headers=kwargs["headers"])
            return httpx.Response(
                200,
                headers={"content-type": "model/gltf-binary"},
                content=b"glTF-test",
                request=httpx.Request("POST", url),
            )

    monkeypatch.setattr("app.hunyuan_client.httpx.Client", Client)
    image = tmp_path / "input.png"
    output = tmp_path / "output.glb"
    image.write_bytes(b"png")

    result = ShapeGenerationClient(get_settings()).generate(image, output)

    assert seen == {
        "url": "https://shape.example.test/generate",
        "headers": {"Authorization": "Bearer secret"},
    }
    assert output.read_bytes() == b"glTF-test"
    assert result["engine"] == "hunyuan3d"
