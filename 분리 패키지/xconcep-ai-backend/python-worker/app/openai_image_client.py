from __future__ import annotations

import base64
import shutil
from pathlib import Path
from typing import Any

import httpx
from PIL import Image, ImageOps

from .generator import generate_2d
from .settings import Settings


class GPTImageClient:
    def __init__(self, settings: Settings):
        self.settings = settings

    def generate_concepts(
        self,
        project_id: str,
        prompt: str,
        category: str,
        image_paths: list[str],
        analysis: dict[str, Any],
    ) -> list[dict[str, Any]]:
        if self.settings.openai_image_mode == "mock":
            return generate_2d(project_id, prompt, category, image_paths)
        if self.settings.openai_image_mode != "openai":
            raise RuntimeError(f"지원하지 않는 OPENAI_IMAGE_MODE: {self.settings.openai_image_mode}")
        if not self.settings.openai_api_key:
            raise RuntimeError("OPENAI_API_KEY 환경변수가 없음")

        project = self.settings.storage_path / "projects" / project_id
        output_dir = project / "concepts"
        output_dir.mkdir(parents=True, exist_ok=True)
        contact_sheet = _make_contact_sheet(image_paths, project / "reference-contact-sheet.png")
        results: list[dict[str, Any]] = []
        variants = analysis.get("concept_variants") or []
        for index, variant in enumerate(variants[:4], start=1):
            output_path = output_dir / f"concept-{index}.png"
            image_prompt = str(variant.get("image_prompt") or prompt)
            image_prompt += "\nPreserve the functional mechanism and engineering constraints from the reference. Generate one product only."
            image_bytes = self._call_api(image_prompt, contact_sheet)
            output_path.write_bytes(image_bytes)
            results.append({
                "id": f"CONCEPT-{index}",
                "title": str(variant.get("name") or f"Option {index}"),
                "description": str(variant.get("design_direction") or "산업 설계 대안"),
                "url": f"{self.settings.public_storage_prefix}/projects/{project_id}/concepts/{output_path.name}",
                "absolute_path": str(output_path),
            })
        return results

    def _call_api(self, prompt: str, reference_image: Path | None) -> bytes:
        headers = {"Authorization": f"Bearer {self.settings.openai_api_key}"}
        timeout = httpx.Timeout(600.0, connect=30.0)
        with httpx.Client(timeout=timeout) as client:
            if reference_image is None:
                response = client.post(
                    "https://api.openai.com/v1/images/generations",
                    headers={**headers, "Content-Type": "application/json"},
                    json={
                        "model": self.settings.openai_image_model,
                        "prompt": prompt,
                        "size": self.settings.openai_image_size,
                        "quality": self.settings.openai_image_quality,
                        "output_format": "png",
                    },
                )
            else:
                with reference_image.open("rb") as image_file:
                    response = client.post(
                        "https://api.openai.com/v1/images/edits",
                        headers=headers,
                        data={
                            "model": self.settings.openai_image_model,
                            "prompt": prompt,
                            "size": self.settings.openai_image_size,
                            "quality": self.settings.openai_image_quality,
                            "output_format": "png",
                        },
                        files={"image": (reference_image.name, image_file, "image/png")},
                    )
            response.raise_for_status()
            payload = response.json()
        item = payload["data"][0]
        if item.get("b64_json"):
            return base64.b64decode(item["b64_json"])
        if item.get("url"):
            with httpx.Client(timeout=120.0) as client:
                download = client.get(item["url"])
                download.raise_for_status()
                return download.content
        raise RuntimeError("GPT Image API 응답에 이미지 데이터가 없음")


def _make_contact_sheet(image_paths: list[str], output_path: Path) -> Path | None:
    paths = [Path(path) for path in image_paths if Path(path).exists()]
    if not paths:
        return None
    cells: list[Image.Image] = []
    for path in paths[:4]:
        with Image.open(path) as source:
            image = ImageOps.exif_transpose(source).convert("RGB")
            image.thumbnail((768, 768))
            canvas = Image.new("RGB", (768, 768), "white")
            x = (768 - image.width) // 2
            y = (768 - image.height) // 2
            canvas.paste(image, (x, y))
            cells.append(canvas)
    if len(cells) == 1:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        cells[0].save(output_path, "PNG")
        return output_path
    sheet = Image.new("RGB", (1536, 1536), "white")
    positions = [(0, 0), (768, 0), (0, 768), (768, 768)]
    for cell, pos in zip(cells, positions):
        sheet.paste(cell, pos)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(output_path, "PNG")
    return output_path
