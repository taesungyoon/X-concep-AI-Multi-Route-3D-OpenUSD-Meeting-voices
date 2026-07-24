from __future__ import annotations

import base64
import json
import mimetypes
import re
from pathlib import Path
from typing import Any

import httpx

from .design_state import extract_prompt_dimensions
from .settings import Settings


SYSTEM_PROMPT = """You are an industrial-design requirement parser for manufacturing equipment.
Return only one valid JSON object. Do not include markdown.
Never invent a confirmed dimension. Unknown values must be null and listed in uncertainties.
The output must be suitable for generating four clean 2D industrial concept renders and one image-to-3D input.
Avoid infographics, text labels, dimension annotations, exploded views, multiple objects, and collage layouts."""


class LocalGemmaClient:
    def __init__(self, settings: Settings):
        self.settings = settings

    def analyze(self, prompt: str, category: str, image_paths: list[str]) -> dict[str, Any]:
        if self.settings.llm_mode in {"mock", "rules"}:
            return self._fallback(prompt, category, image_paths)
        if self.settings.llm_mode not in {"vllm", "openai_compatible", "ollama"}:
            raise RuntimeError(f"지원하지 않는 LLM_MODE: {self.settings.llm_mode}")

        content: list[dict[str, Any]] = [
            {
                "type": "text",
                "text": self._user_prompt(prompt, category, len(image_paths)),
            }
        ]
        for image_path in image_paths[:4]:
            path = Path(image_path)
            if path.exists():
                content.append({"type": "image_url", "image_url": {"url": _data_uri(path)}})

        payload = {
            "model": self.settings.gemma_model_name,
            "temperature": 0.15,
            "max_tokens": 2200,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": content},
            ],
        }
        headers = {"Authorization": f"Bearer {self.settings.vllm_api_key}", "Content-Type": "application/json"}
        with httpx.Client(timeout=self.settings.llm_timeout_seconds) as client:
            response = client.post(f"{self.settings.vllm_base_url}/chat/completions", headers=headers, json=payload)
            response.raise_for_status()
        data = response.json()
        text = data["choices"][0]["message"]["content"]
        parsed = _parse_json(text)
        return self._normalize(parsed, prompt, category, image_paths)

    def _user_prompt(self, prompt: str, category: str, image_count: int) -> str:
        schema = {
            "project_summary": "string",
            "category": category,
            "functional_purpose": "string",
            "operating_principle": "string",
            "main_components": ["string"],
            "constraints": ["string"],
            "dimensions": {"width_mm": None, "depth_mm": None, "height_mm": None},
            "materials": ["string"],
            "safety_features": ["string"],
            "visual_requirements": ["string"],
            "negative_requirements": ["string"],
            "uncertainties": ["string"],
            "concept_variants": [
                {"id": "A", "name": "string", "design_direction": "string", "image_prompt": "string"},
                {"id": "B", "name": "string", "design_direction": "string", "image_prompt": "string"},
                {"id": "C", "name": "string", "design_direction": "string", "image_prompt": "string"},
                {"id": "D", "name": "string", "design_direction": "string", "image_prompt": "string"},
            ],
        }
        return (
            f"Category: {category}\nReference image count: {image_count}\n"
            f"User requirement:\n{prompt}\n\n"
            "Analyze the requirement and return this JSON shape exactly:\n"
            + json.dumps(schema, ensure_ascii=False)
        )

    def _normalize(self, value: dict[str, Any], prompt: str, category: str, image_paths: list[str]) -> dict[str, Any]:
        fallback = self._fallback(prompt, category, image_paths)
        for key, default in fallback.items():
            if key not in value or value[key] in (None, "", []):
                value[key] = default
        dimensions = value.get("dimensions")
        if not isinstance(dimensions, dict):
            dimensions = {}
        for key, parsed in extract_prompt_dimensions(prompt).items():
            if key == "length_mm":
                continue
            if dimensions.get(key) in (None, "") and parsed is not None:
                dimensions[key] = parsed
        value["dimensions"] = dimensions
        variants = value.get("concept_variants")
        if not isinstance(variants, list) or len(variants) < 4:
            value["concept_variants"] = fallback["concept_variants"]
        else:
            value["concept_variants"] = variants[:4]
        value["category"] = category
        return value

    def _fallback(self, prompt: str, category: str, image_paths: list[str]) -> dict[str, Any]:
        category_name = {"equipment": "industrial automation equipment", "module": "single industrial module", "part": "mechanical part"}[category]
        negative = [
            "no infographic", "no text labels", "no dimensions", "no exploded view",
            "no multiple objects", "no collage", "single centered product", "clean background",
        ]
        directions = {
            "part": [
                ("Datum", "dimension-faithful part with every requested hole and rib visible"),
                ("Service", "the same required geometry with practical tool access"),
                ("Rigid", "the same required geometry with only requested reinforcement"),
                ("Production", "the same required geometry with a production-ready metal finish"),
            ],
            "module": [
                ("Datum", "dimension-faithful module with exact requested component counts"),
                ("Service", "the same required module with maintenance access"),
                ("Rigid", "the same required module with a manufacturable support layout"),
                ("Production", "the same required module with production-grade organization"),
            ],
            "equipment": [
                ("Datum", "dimension-faithful equipment with every requested component and count"),
                ("Service", "the same required equipment with realistic service access"),
                ("Rigid", "the same required equipment on a manufacturable frame"),
                ("Production", "the same required equipment with preserved safety requirements"),
            ],
        }[category]
        variants = []
        for idx, (name, direction) in enumerate(directions, start=1):
            variants.append({
                "id": chr(64 + idx),
                "name": name,
                "design_direction": direction,
                "image_prompt": (
                    f"Photorealistic industrial product concept render of a {category_name}. "
                    f"Requirement: {prompt}. Design direction: {direction}. "
                    "Hard constraints: preserve stated component counts, spatial relations, and numeric proportions; "
                    "do not add unrequested major components. "
                    "Single isolated product, three-quarter front perspective, manufacturable mechanical structure, "
                    "realistic metal and polycarbonate materials, neutral dark studio background, no people, no text, no labels, no dimensions."
                ),
            })
        prompt_dimensions = extract_prompt_dimensions(prompt)
        dimensions = {
            key: prompt_dimensions.get(key)
            for key in ("width_mm", "depth_mm", "height_mm")
        }
        return {
            "project_summary": prompt[:240],
            "category": category,
            "functional_purpose": prompt,
            "operating_principle": "사용자 요구사항에 기반한 기계적 구동 및 작업 흐름",
            "main_components": ["base frame", "working unit", "drive unit", "control unit"],
            "constraints": [],
            "dimensions": dimensions,
            "materials": ["industrial steel", "aluminum profile", "polycarbonate safety cover"],
            "safety_features": ["guarding", "emergency stop provision"],
            "visual_requirements": ["single object", "manufacturable", "industrial product render"],
            "negative_requirements": negative,
            "uncertainties": (
                ["표준 부품 규격은 별도 확인이 필요함"]
                if all(value is not None for value in dimensions.values())
                else ["정확한 치수와 표준 부품 규격은 별도 확인이 필요함"]
            ) if not image_paths else [],
            "concept_variants": variants,
        }


def _data_uri(path: Path) -> str:
    mime = mimetypes.guess_type(path.name)[0] or "image/png"
    return f"data:{mime};base64,{base64.b64encode(path.read_bytes()).decode('ascii')}"


def _parse_json(text: str) -> dict[str, Any]:
    try:
        value = json.loads(text)
        if isinstance(value, dict):
            return value
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise RuntimeError("Gemma 응답에서 JSON 객체를 찾을 수 없음")
    value = json.loads(match.group(0))
    if not isinstance(value, dict):
        raise RuntimeError("Gemma 응답이 JSON 객체가 아님")
    return value
