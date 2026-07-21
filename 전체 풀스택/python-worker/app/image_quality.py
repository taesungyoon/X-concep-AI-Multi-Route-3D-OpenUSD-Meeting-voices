from __future__ import annotations

from io import BytesIO
from typing import Any

from PIL import Image, ImageStat

from .settings import Settings


def validate_generated_image(
    image_bytes: bytes,
    settings: Settings,
    *,
    expected_size: tuple[int, int],
) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    try:
        with Image.open(BytesIO(image_bytes)) as source:
            source.verify()
        with Image.open(BytesIO(image_bytes)) as source:
            image = source.convert("RGB")
            width, height = image.size
            sample = image.copy()
            sample.thumbnail((256, 256))
            channel_stddev = [round(value, 3) for value in ImageStat.Stat(sample).stddev]
            fmt = source.format or "unknown"
    except Exception as exc:
        return {
            "passed": False,
            "checks": [{"id": "decodable", "passed": False, "detail": type(exc).__name__}],
            "metrics": {},
        }

    checks.append({"id": "decodable", "passed": True, "detail": fmt})
    checks.append({
        "id": "minimum_dimensions",
        "passed": width >= settings.image_min_width and height >= settings.image_min_height,
        "detail": {"width": width, "height": height},
    })
    checks.append({
        "id": "minimum_file_size",
        "passed": len(image_bytes) >= settings.image_min_file_bytes,
        "detail": len(image_bytes),
    })
    checks.append({
        "id": "non_blank_channels",
        "passed": max(channel_stddev) >= settings.image_min_channel_stddev,
        "detail": channel_stddev,
    })
    expected_width, expected_height = expected_size
    actual_aspect = width / max(height, 1)
    expected_aspect = expected_width / max(expected_height, 1)
    aspect_error = abs(actual_aspect - expected_aspect) / expected_aspect
    checks.append({
        "id": "expected_aspect",
        "passed": not settings.image_require_expected_aspect or aspect_error <= 0.03,
        "detail": {"expected": round(expected_aspect, 5), "actual": round(actual_aspect, 5)},
    })
    return {
        "passed": all(check["passed"] for check in checks),
        "checks": checks,
        "metrics": {
            "width": width,
            "height": height,
            "bytes": len(image_bytes),
            "channel_stddev": channel_stddev,
        },
    }
