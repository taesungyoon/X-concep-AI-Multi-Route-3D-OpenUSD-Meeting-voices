from app.llm_client import LocalGemmaClient


def test_rules_fallback_preserves_number_first_dimensions():
    client = LocalGemmaClient.__new__(LocalGemmaClient)

    analysis = client._fallback(
        "1600mm width, 1000mm depth, 1800mm height vision inspection equipment",
        "equipment",
        [],
    )

    assert analysis["dimensions"] == {
        "width_mm": 1600.0,
        "depth_mm": 1000.0,
        "height_mm": 1800.0,
    }
    assert analysis["uncertainties"] == ["표준 부품 규격은 별도 확인이 필요함"]
