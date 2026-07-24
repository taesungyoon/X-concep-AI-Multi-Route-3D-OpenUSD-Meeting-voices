from pathlib import Path

from app.models import Generate2DRequest, Generate3DRequest
from app.openusd_exporter import validate_usda
from app.pipeline import GenerationPipeline
from app.settings import get_settings


def test_mock_pipeline(monkeypatch, tmp_path):
    monkeypatch.setenv("STORAGE_PATH", str(tmp_path))
    monkeypatch.setenv("LLM_MODE", "mock")
    monkeypatch.setenv("OPENAI_IMAGE_MODE", "mock")
    monkeypatch.setenv("HUNYUAN_MODE", "mock")
    monkeypatch.setenv("OPENUSD_GENERATE_USDC", "false")
    pipeline = GenerationPipeline(get_settings())
    request_2d = Generate2DRequest(
        project_id="PRJ-TEST",
        prompt="서보모터 구동형 FPCB 벤딩 단일 유닛을 설계함",
        category="equipment",
        image_paths=[],
    )
    result_2d = pipeline.generate_2d(request_2d)
    assert len(result_2d["results"]) == 4
    assert result_2d["analysis"]["image_requirements"]
    assert result_2d["analysis"]["design_spec"]["category"] == "equipment"
    selected = result_2d["results"][0]
    request_3d = Generate3DRequest(
        project_id="PRJ-TEST",
        prompt=request_2d.prompt,
        category="equipment",
        selected_2d_id=selected["id"],
        selected_image_path=selected["absolute_path"],
    )
    result_3d = pipeline.generate_3d(request_3d)
    assert Path(result_3d["absolute_paths"]["glb"]).exists()
    assert Path(result_3d["absolute_paths"]["stl"]).exists()
    usda = Path(result_3d["absolute_paths"]["usda"])
    assert usda.exists()
    validation = validate_usda(usda)
    assert validation["valid_header"] is True
    assert validation["mesh_count"] > 0
