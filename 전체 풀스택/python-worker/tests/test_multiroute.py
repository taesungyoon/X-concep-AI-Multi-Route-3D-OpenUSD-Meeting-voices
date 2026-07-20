from pathlib import Path

from app.generation_router import plan_generation
from app.design_state import build_design_state
from app.models import Generate2DRequest, Generate3DRequest
from app.pipeline import GenerationPipeline
from app.settings import get_settings


def build_pipeline(monkeypatch, tmp_path):
    monkeypatch.setenv("STORAGE_PATH", str(tmp_path))
    monkeypatch.setenv("LLM_MODE", "mock")
    monkeypatch.setenv("OPENAI_IMAGE_MODE", "mock")
    monkeypatch.setenv("HUNYUAN_MODE", "mock")
    monkeypatch.setenv("OPENSCAD_MODE", "mock")
    monkeypatch.setenv("BLENDER_MODE", "mock")
    monkeypatch.setenv("OPENUSD_GENERATE_USDC", "true")
    return GenerationPipeline(get_settings())


def test_router_structural_and_hybrid():
    state = build_design_state(
        project_id="PRJ-R",
        revision=1,
        prompt="폭 900mm 프레임과 브래킷, 인체공학 곡면 손잡이를 포함한 설비",
        category="equipment",
        selected_2d_id="CONCEPT-1",
        meeting_analysis={"dimensions": {"width_mm": 900, "depth_mm": 600, "height_mm": 1200}},
    )
    plan = plan_generation(state, "auto", "standard", None, True)
    assert plan["primary_route"] == "openscad"
    assert "hunyuan3d" in plan["secondary_routes"]
    assert "blender" in plan["postprocess"]


def test_structural_route_generates_scad_and_validation(monkeypatch, tmp_path):
    pipeline = build_pipeline(monkeypatch, tmp_path)
    prompt = "폭 900mm, 깊이 600mm, 높이 1200mm의 브래킷 프레임 구조"
    two_d = pipeline.generate_2d(Generate2DRequest(project_id="PRJ-S", prompt=prompt, category="equipment"))
    selected = two_d["results"][0]
    result = pipeline.generate_3d(Generate3DRequest(
        project_id="PRJ-S",
        prompt=prompt,
        category="equipment",
        selected_2d_id=selected["id"],
        selected_image_path=selected["absolute_path"],
        output_goal="structural",
        quality_profile="standard",
        source_analysis={"dimensions": {"width_mm": 900, "depth_mm": 600, "height_mm": 1200}},
    ))
    assert result["route_key"] == "structural"
    assert result["assets"]["structural"]["scad_url"].startswith("/storage/projects/")
    assert Path(tmp_path / "projects/PRJ-S/result/structural/model.scad").exists()
    assert result["validation_grade"] in {"structured", "validated"}
    assert result["design_state"]["consistency_contract"]["priority"][0] == "functional_match"


def test_high_quality_route_keeps_multiple_assets(monkeypatch, tmp_path):
    pipeline = build_pipeline(monkeypatch, tmp_path)
    prompt = "곡면 커버와 프레임을 포함한 고품질 산업용 장비"
    two_d = pipeline.generate_2d(Generate2DRequest(project_id="PRJ-H", prompt=prompt, category="equipment"))
    selected = two_d["results"][0]
    result = pipeline.generate_3d(Generate3DRequest(
        project_id="PRJ-H", prompt=prompt, category="equipment",
        selected_2d_id=selected["id"], selected_image_path=selected["absolute_path"],
        output_goal="high_quality", quality_profile="final",
    ))
    assert "high_quality" in result["assets"]
    assert result["active_asset"] == "high_quality"
    assert result["openusd_root_url"]
    assert result["regeneration_actions"]
