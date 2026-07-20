from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


def create_preview(glb_path: Path, reference_image: Path, output_path: Path, blender_bin: str = "") -> str:
    if blender_bin and Path(blender_bin).exists():
        script = Path(__file__).resolve().parents[1] / "scripts" / "render_glb.py"
        subprocess.run(
            [blender_bin, "--background", "--python", str(script), "--", str(glb_path), str(output_path)],
            check=True,
            timeout=600,
        )
        if output_path.exists():
            return "blender"
    _fallback_preview(reference_image, output_path)
    return "reference_fallback"


def _fallback_preview(reference_image: Path, output_path: Path) -> None:
    with Image.open(reference_image) as source:
        image = source.convert("RGB")
        image.thumbnail((1280, 760))
    canvas = Image.new("RGB", (1280, 860), "#06131f")
    x = (1280 - image.width) // 2
    y = 50 + (710 - image.height) // 2
    canvas.paste(image, (x, y))
    draw = ImageDraw.Draw(canvas)
    draw.rectangle((0, 780, 1280, 860), fill="#091c2b")
    draw.text((45, 802), "3D GLB 생성 완료 · 실제 형상은 웹 3D 뷰어에서 확인함", fill="#8adff0")
    draw.text((45, 831), "Blender 경로를 설정하면 서버에서 3D 렌더 PNG도 자동 생성함", fill="#7690a3")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output_path, "PNG")
