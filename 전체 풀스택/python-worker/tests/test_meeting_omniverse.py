import json
from pathlib import Path

from app.models import MeetingAnalyzeRequest, MeetingTranscribeRequest, Generate3DRequest
from app.pipeline import GenerationPipeline
from app.settings import get_settings


def build_pipeline(monkeypatch, tmp_path):
    monkeypatch.setenv("STORAGE_PATH", str(tmp_path))
    monkeypatch.setenv("LLM_MODE", "mock")
    monkeypatch.setenv("OPENAI_IMAGE_MODE", "mock")
    monkeypatch.setenv("HUNYUAN_MODE", "mock")
    monkeypatch.setenv("SPEECH_MODE", "mock")
    monkeypatch.setenv("OPENUSD_GENERATE_USDC", "false")
    monkeypatch.setenv("OMNIVERSE_GENERATE_LAYERS", "true")
    monkeypatch.setenv("OMNIVERSE_ENABLE_PHYSICS", "true")
    monkeypatch.setenv("OMNIVERSE_ENABLE_VARIANTS", "true")
    return GenerationPipeline(get_settings())


def test_mock_meeting_transcribe_and_analyze(monkeypatch, tmp_path):
    pipeline = build_pipeline(monkeypatch, tmp_path)
    audio = tmp_path / "projects" / "PRJ-MEET1" / "meeting" / "audio" / "chunk.webm"
    audio.parent.mkdir(parents=True, exist_ok=True)
    audio.write_bytes(b"mock-audio")
    transcribed = pipeline.transcribe_meeting(MeetingTranscribeRequest(
        project_id="PRJ-MEET1", audio_path=str(audio), chunk_index=0, language="ko"
    ))
    assert transcribed["segments"]
    analyzed = pipeline.analyze_meeting(MeetingAnalyzeRequest(
        project_id="PRJ-MEET1",
        category="equipment",
        transcript="폭은 800밀리미터 이내이며 서보모터와 투명 안전커버를 적용해주세요.",
        segments=[],
    ))
    assert analyzed["analysis"]["dimensions"]["width_mm"] == 800
    assert "서보모터" in analyzed["analysis"]["generation_prompt"]


def test_openusd_layered_package_contains_omniverse_capabilities(monkeypatch, tmp_path):
    pipeline = build_pipeline(monkeypatch, tmp_path)
    result = pipeline.generate_3d(Generate3DRequest(
        project_id="PRJ-USDMEET",
        prompt="서보모터 구동형 단일 벤딩 유닛과 투명 안전커버",
        category="equipment",
        selected_2d_id="CONCEPT-1",
        meeting_analysis={"summary": "안전커버와 서보모터를 확정함", "revision_note": "회의 반영"},
        revision=2,
    ))
    root = tmp_path / "projects" / "PRJ-USDMEET" / "result" / "openusd" / "root.usda"
    manifest = root.parent / "manifest.json"
    assert root.exists()
    assert manifest.exists()
    text = root.read_text(encoding="utf-8")
    assert "subLayers" in text
    assert "designOption" in text
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    assert payload["capabilities"]["kit_webrtc_streaming"] is True
    assert payload["capabilities"]["physx_ready"] is True
    assert result["openusd_root_url"].endswith("root.usda")

def test_meeting_fallback_marks_unresolved_dimension(monkeypatch, tmp_path):
    from app.meeting_analyzer import MeetingAnalyzer
    settings = build_pipeline(monkeypatch, tmp_path).settings
    result=MeetingAnalyzer(settings).analyze('전체 폭은 900 mm로 변경하고 높이는 다음 회의에서 확정함.', 'equipment')
    assert result['dimensions']['width_mm']==900
    assert any('높이' in item for item in result['unresolved_items'])
    assert any(item['field']=='width_mm' for item in result['requested_changes'])
