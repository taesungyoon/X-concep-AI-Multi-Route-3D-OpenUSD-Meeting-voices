import base64
import io

import pytest
from fastapi import HTTPException
from PIL import Image

from app.shape_adapter import _authorize, _prompt, _rgba_image


def test_adapter_contract(monkeypatch):
    monkeypatch.setattr("app.shape_adapter.SHAPE_API_KEY", "secret")
    with pytest.raises(HTTPException) as denied:
        _authorize("Bearer wrong")
    assert denied.value.status_code == 401
    _authorize("Bearer secret")

    source = io.BytesIO()
    Image.new("RGB", (32, 48), "red").save(source, "PNG")
    converted = Image.open(io.BytesIO(_rgba_image(base64.b64encode(source.getvalue()).decode())))
    assert converted.mode == "RGBA"
    assert converted.size == (32, 48)

    prompt = _prompt("input.png")
    assert prompt["2"]["inputs"]["image"] == ["1", 0]
    assert prompt["2"]["inputs"]["mask"] == ["1", 1]
    assert prompt["2"]["inputs"]["steps"] == 80
    assert prompt["3"]["class_type"] == "Preview3D"
