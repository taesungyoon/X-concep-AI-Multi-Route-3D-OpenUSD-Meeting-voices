from __future__ import annotations

import json
import re
from typing import Any

import httpx

from .settings import Settings


MEETING_SYSTEM_PROMPT = """You analyze Korean manufacturing-equipment meetings.
Return only one valid JSON object and no markdown.
Separate confirmed decisions, requested changes, unresolved items, dimensions, components, safety requirements, and action items.
Never convert an uncertain statement into a confirmed fact.
Create generation_prompt as a concise but complete Korean prompt for industrial 2D concept generation.
Create usd_metadata values for OpenUSD custom attributes and revision notes."""


class MeetingAnalyzer:
    def __init__(self, settings: Settings):
        self.settings = settings

    def analyze(
        self,
        transcript: str,
        category: str,
        previous_analysis: dict[str, Any] | None = None,
        retrieval_context: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        if self.settings.llm_mode == "mock":
            return self._fallback(transcript, category, previous_analysis)
        schema = {
            "summary": "string",
            "confirmed_requirements": ["string"],
            "requested_changes": [{"field": "string", "old": None, "new": "string", "confidence": 0.0}],
            "dimensions": {"width_mm": None, "depth_mm": None, "height_mm": None},
            "components": ["string"],
            "operating_principle": "string",
            "safety_requirements": ["string"],
            "unresolved_items": ["string"],
            "action_items": [{"owner": "string", "task": "string"}],
            "generation_prompt": "string",
            "revision_note": "string",
            "usd_metadata": {"meeting_summary": "string", "decision_count": 0, "unresolved_count": 0},
        }
        user = (
            f"Category: {category}\nPrevious analysis:\n{json.dumps(previous_analysis or {}, ensure_ascii=False)}\n\n"
            f"Retrieved manufacturing context (reference only, never override explicit meeting decisions):\n"
            f"{json.dumps(retrieval_context or [], ensure_ascii=False)}\n\n"
            f"Meeting transcript:\n{transcript}\n\nReturn exactly this JSON shape:\n{json.dumps(schema, ensure_ascii=False)}"
        )
        payload = {
            "model": self.settings.gemma_model_name,
            "temperature": 0.1,
            "max_tokens": 2600,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": MEETING_SYSTEM_PROMPT},
                {"role": "user", "content": user},
            ],
        }
        headers = {"Authorization": f"Bearer {self.settings.vllm_api_key}", "Content-Type": "application/json"}
        with httpx.Client(timeout=self.settings.llm_timeout_seconds) as client:
            response = client.post(f"{self.settings.vllm_base_url}/chat/completions", headers=headers, json=payload)
            response.raise_for_status()
        text = response.json()["choices"][0]["message"]["content"]
        value = _parse_json(text)
        return self._normalize(value, transcript, category, previous_analysis)

    def create_patch(self, transcript: str, current_analysis: dict[str, Any], base_revision: int) -> dict[str, Any]:
        latest = self.analyze(transcript, current_analysis.get("category", "equipment"), current_analysis)
        operations = []
        old_dimensions = current_analysis.get("dimensions") or {}
        new_dimensions = latest.get("dimensions") or {}
        for key in ("width_mm", "depth_mm", "height_mm"):
            old = old_dimensions.get(key)
            new = new_dimensions.get(key)
            if new is not None and new != old:
                operations.append({"op": "replace", "path": f"/dimensions/{key}", "old": old, "value": new})
        if latest.get("generation_prompt") != current_analysis.get("generation_prompt"):
            operations.append({
                "op": "replace",
                "path": "/generation_prompt",
                "old": current_analysis.get("generation_prompt"),
                "value": latest.get("generation_prompt"),
            })
        return {
            "base_revision": base_revision,
            "next_revision": base_revision + 1,
            "operations": operations,
            "analysis": latest,
            "revision_note": latest.get("revision_note") or "회의 내용 변경 반영",
        }

    def _normalize(self, value: dict[str, Any], transcript: str, category: str, previous: dict[str, Any] | None) -> dict[str, Any]:
        fallback = self._fallback(transcript, category, previous)
        for key, default in fallback.items():
            if key not in value or value[key] in (None, ""):
                value[key] = default
        value["category"] = category
        value["usd_metadata"] = value.get("usd_metadata") or fallback["usd_metadata"]
        return value

    @staticmethod
    def _fallback(transcript: str, category: str, previous: dict[str, Any] | None) -> dict[str, Any]:
        compact = " ".join(transcript.split())
        dims = {"width_mm": None, "depth_mm": None, "height_mm": None}
        patterns = {
            "width_mm": r"(?:폭|가로)\s*(?:은|를|:)?\s*(\d{2,5})\s*(?:mm|밀리미터)?",
            "depth_mm": r"(?:깊이|세로)\s*(?:은|를|:)?\s*(\d{2,5})\s*(?:mm|밀리미터)?",
            "height_mm": r"(?:높이)\s*(?:은|를|:)?\s*(\d{2,5})\s*(?:mm|밀리미터)?",
        }
        for key, pattern in patterns.items():
            match = re.search(pattern, compact, re.IGNORECASE)
            if match:
                dims[key] = int(match.group(1))
        requirements = []
        for keyword in ["서보모터", "안전커버", "제어반", "전면 투입", "90도", "단일 유닛", "비전 카메라", "컨베이어"]:
            if keyword in compact:
                requirements.append(keyword)
        unresolved = []
        dimension_labels = {"width_mm": "폭", "depth_mm": "깊이", "height_mm": "높이"}
        uncertainty_words = ("미정", "추후", "다음 회의", "나중", "확정 필요", "검토 필요")
        for key, label in dimension_labels.items():
            if dims[key] is None and label in compact and any(word in compact for word in uncertainty_words):
                unresolved.append(f"{label} 치수 확정이 필요함")
        if all(value is None for value in dims.values()) and not unresolved:
            unresolved.append("전체 외형 치수 확인이 필요함")
        requested_changes = []
        if "변경" in compact:
            for key, label in dimension_labels.items():
                if dims[key] is not None:
                    requested_changes.append({"field": key, "old": None, "new": dims[key], "confidence": 0.8})
        prompt = compact[:1800]
        if requirements:
            prompt += ". 핵심 구성: " + ", ".join(requirements)
        return {
            "category": category,
            "summary": compact[:320],
            "confirmed_requirements": requirements,
            "requested_changes": requested_changes,
            "dimensions": dims,
            "components": requirements or ["base frame", "working unit", "drive unit", "control unit"],
            "operating_principle": "회의에서 합의한 제조 공정과 구동 요구사항을 반영함",
            "safety_requirements": [x for x in requirements if "안전" in x] or [],
            "unresolved_items": unresolved,
            "action_items": [],
            "generation_prompt": prompt,
            "revision_note": "회의 음성 분석 결과 반영",
            "usd_metadata": {
                "meeting_summary": compact[:500],
                "decision_count": len(requirements),
                "unresolved_count": len(unresolved),
            },
        }


def _parse_json(text: str) -> dict[str, Any]:
    try:
        value = json.loads(text)
        if isinstance(value, dict):
            return value
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise RuntimeError("회의 분석 응답에서 JSON 객체를 찾을 수 없음")
    value = json.loads(match.group(0))
    if not isinstance(value, dict):
        raise RuntimeError("회의 분석 응답이 JSON 객체가 아님")
    return value
