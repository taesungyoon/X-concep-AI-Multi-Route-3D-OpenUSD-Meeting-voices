from pathlib import Path

import pytest
from pxr import Usd

from app.models import Generate2DRequest, Generate3DRequest
from app.pipeline import GenerationPipeline
from app.settings import get_settings


def build_pipeline(monkeypatch, tmp_path, *, usdc: bool = True):
    monkeypatch.setenv("STORAGE_PATH", str(tmp_path))
    monkeypatch.setenv("LLM_MODE", "mock")
    monkeypatch.setenv("OPENAI_IMAGE_MODE", "mock")
    monkeypatch.setenv("HUNYUAN_MODE", "mock")
    monkeypatch.setenv("SPEECH_MODE", "mock")
    monkeypatch.setenv("OPENUSD_GENERATE_USDC", "true" if usdc else "false")
    monkeypatch.setenv("OMNIVERSE_GENERATE_LAYERS", "true")
    monkeypatch.setenv("OMNIVERSE_ENABLE_PHYSICS", "true")
    monkeypatch.setenv("OMNIVERSE_ENABLE_VARIANTS", "true")
    return GenerationPipeline(get_settings())


def test_storage_path_traversal_is_blocked(monkeypatch, tmp_path):
    pipeline = build_pipeline(monkeypatch, tmp_path)
    with pytest.raises(ValueError, match="STORAGE_PATH"):
        pipeline._resolve_path("../../etc/passwd")
    with pytest.raises(ValueError, match="STORAGE_PATH"):
        pipeline._resolve_path("/etc/passwd")
    with pytest.raises(ValueError, match="STORAGE_PATH"):
        pipeline._resolve_path(r"C:\Windows\System32\drivers\etc\hosts")
    with pytest.raises(ValueError, match="STORAGE_PATH"):
        pipeline._resolve_path(r"\\server\share\asset.glb")


def test_openusd_text_binary_and_layered_stages_parse(monkeypatch, tmp_path):
    pipeline = build_pipeline(monkeypatch, tmp_path, usdc=True)
    prompt = "서보모터 구동과 투명 안전커버를 적용한 단일 벤딩 유닛 설비"
    result_2d = pipeline.generate_2d(Generate2DRequest(
        project_id="PRJ-PARSER",
        prompt=prompt,
        category="equipment",
    ))
    selected = result_2d["results"][0]
    result_3d = pipeline.generate_3d(Generate3DRequest(
        project_id="PRJ-PARSER",
        prompt=prompt,
        category="equipment",
        selected_2d_id=selected["id"],
        selected_image_path=selected["absolute_path"],
        meeting_analysis={
            "summary": "폭 900mm와 서보모터 적용을 확정함",
            "requested_changes": ["폭 800mm에서 900mm로 변경함"],
            "revision_note": "회의 변경사항 반영함",
        },
        revision=2,
    ))

    usda = Path(result_3d["absolute_paths"]["usda"])
    usdc = Path(result_3d["absolute_paths"]["usdc"])
    root = usda.parent / "openusd" / "root.usda"
    for stage_path in (usda, usdc, root):
        stage = Usd.Stage.Open(str(stage_path))
        assert stage is not None
        assert str(stage.GetDefaultPrim().GetPath()) == "/World"
        assert sum(1 for prim in stage.Traverse() if prim.GetTypeName() == "Mesh") > 0

    root_stage = Usd.Stage.Open(str(root))
    asset = root_stage.GetPrimAtPath("/World/Asset")
    assert asset.GetVariantSets().GetVariantSelection("designOption") == "Selected"
    assert result_3d["openusd_validation"]["parser_valid"] is True
    assert result_3d["openusd_package_validation"]["parser_valid"] is True
