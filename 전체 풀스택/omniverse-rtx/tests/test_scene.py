from __future__ import annotations

import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scene import RENDER_PRODUCT_PATH, validation_stage_usda


def test_validation_stage_has_fixed_render_pipeline() -> None:
    stage = validation_stage_usda(1280, 720)
    assert 'rel camera = </OVCamera>' in stage
    assert 'uniform int2 resolution = (1280, 720)' in stage
    assert f'rel products = [<{RENDER_PRODUCT_PATH}>]' in stage
    assert 'uniform string sourceName = "LdrColor"' in stage


def test_validation_stage_clamps_invalid_resolution() -> None:
    stage = validation_stage_usda(0, -4)
    assert 'uniform int2 resolution = (1, 1)' in stage
