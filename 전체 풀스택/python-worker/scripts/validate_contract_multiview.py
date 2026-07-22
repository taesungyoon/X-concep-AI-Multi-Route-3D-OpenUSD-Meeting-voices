from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path

from app.contract_validation import validate_contract_multiview
from app.design_state import build_design_state
from app.parametric_generators import (
    EQUIPMENT_MODE,
    MODE_FOR_CATEGORY,
    apply_partial_regeneration,
    build_geometry_contract,
)


CASES = {
    "part": (
        "폭 240mm 깊이 160mm 높이 120mm L자형 알루미늄 센서 브래킷. "
        "수직판 중앙에 센서 홀 1개, 베이스판에 체결 홀 4개, 양측 삼각 리브 2개"
    ),
    "module": (
        "폭 800mm 깊이 600mm 높이 900mm 베이스 플레이트 위 리니어 가이드 2개와 "
        "서보모터 2개, 작업 지그와 센서 1개를 포함한 구동 모듈"
    ),
    "equipment": (
        "폭 1600mm 깊이 1000mm 높이 1800mm 알루미늄 프로파일 프레임 내부에 "
        "컨베이어 1대와 서보모터 2개, 컨베이어 위 비전 카메라 1개를 배치하고 "
        "전면 투명 안전도어와 우측 제어반을 포함함"
    ),
}


def build_contract(category: str, prompt: str):
    state = build_design_state(
        project_id=f"PRJ-MULTIVIEW-{category.upper()}",
        revision=1,
        prompt=prompt,
        category=category,
        selected_2d_id="CONCEPT-1",
        source_analysis={"dimensions": {}},
    )
    return build_geometry_contract(state, category, MODE_FOR_CATEGORY[category])


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    case_results = {}
    all_passed = True
    for category, prompt in CASES.items():
        contract = build_contract(category, prompt)
        case_dir = args.output_dir / category
        report = validate_contract_multiview(contract, case_dir / "views")
        case_results[category] = {
            "passed": report["passed"],
            "score": report["score"],
            "views": report["views"],
            "checks": report["checks"],
            "regeneration_plan": report["regeneration_plan"],
            "contract_sha256": contract["contract_sha256"],
        }
        all_passed = all_passed and report["passed"]

    equipment = build_contract("equipment", CASES["equipment"])
    failed = copy.deepcopy(equipment)
    for component in failed["components"]:
        if component.get("requirement_id") == "vision_camera":
            component["center_mm"][2] = 700.0
    failed_report = validate_contract_multiview(
        failed,
        args.output_dir / "injected_failure" / "views",
    )
    scope = failed_report["regeneration_plan"]["scopes"]
    repaired = apply_partial_regeneration(
        equipment,
        build_contract("equipment", CASES["equipment"]),
        scope,
    )
    partial = repaired.get("partial_regeneration") or {}
    partial_passed = (
        failed_report["passed"] is False
        and scope == ["vision_camera"]
        and partial.get("applied") is True
        and all(
            item["passed"]
            for item in repaired["requirement_coverage"]["components"]
        )
    )
    all_passed = all_passed and partial_passed

    summary = {
        "schema": "xconcep.multiview-evidence/1.0",
        "passed": all_passed,
        "cases": case_results,
        "injected_failure": {
            "passed": failed_report["passed"],
            "scope": scope,
            "checks": failed_report["checks"],
        },
        "partial_regeneration": partial,
    }
    (args.output_dir / "MULTIVIEW_VALIDATION_REPORT.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    lines = [
        "# Multi-view Contract Validation",
        "",
        f"- Overall: {'PASS' if all_passed else 'FAIL'}",
        "- Views: FRONT / TOP / RIGHT",
        "- Validation type: deterministic GeometryContract projection; not independent semantic evaluation",
        "",
        "## Category results",
        "",
    ]
    for category, result in case_results.items():
        lines.append(f"- {category}: {'PASS' if result['passed'] else 'FAIL'} · score {result['score']:.3f}")
    lines.extend([
        "",
        "## Injected failure and partial regeneration",
        "",
        f"- Injected camera-below-conveyor relation: {'detected' if not failed_report['passed'] else 'missed'}",
        f"- Recommended scope: {', '.join(scope) or 'none'}",
        f"- Partial replacement applied: {partial.get('applied') is True}",
        f"- Preserved component count: {len(partial.get('preserved_component_ids') or [])}",
        f"- Regenerated component count: {len(partial.get('regenerated_component_ids') or [])}",
    ])
    (args.output_dir / "MULTIVIEW_VALIDATION_REPORT.md").write_text(
        "\n".join(lines) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"passed": all_passed, "case_scores": {key: value["score"] for key, value in case_results.items()}, "failure_scope": scope, "partial_applied": partial.get("applied")}, ensure_ascii=False))
    return 0 if all_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
