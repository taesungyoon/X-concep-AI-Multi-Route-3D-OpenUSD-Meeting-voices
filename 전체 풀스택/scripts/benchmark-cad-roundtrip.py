from __future__ import annotations

import argparse
import json
import math
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from build123d import GeomType, export_step, import_step

from cad_roundtrip_fixture import CASE_COUNT, build_case, case_spec


STACK_ROOT = Path(__file__).resolve().parents[1]


def _intersection_volume(solids: list[Any]) -> float:
    total = 0.0
    for left_index, left in enumerate(solids):
        for right in solids[left_index + 1 :]:
            left_box = left.bounding_box()
            right_box = right.bounding_box()
            axis_overlaps = (
                min(left_box.max.X, right_box.max.X) - max(left_box.min.X, right_box.min.X),
                min(left_box.max.Y, right_box.max.Y) - max(left_box.min.Y, right_box.min.Y),
                min(left_box.max.Z, right_box.max.Z) - max(left_box.min.Z, right_box.min.Z),
            )
            if any(overlap <= 0.0 for overlap in axis_overlaps):
                continue
            try:
                total += abs(float((left & right).volume))
            except Exception:
                return math.inf
    return total


def _metrics(shape: Any) -> dict[str, Any]:
    solids = list(shape.solids())
    bounds = shape.bounding_box()
    return {
        "valid": bool(shape.is_valid),
        "solid_count": len(solids),
        "face_count": len(shape.faces()),
        "edge_count": len(shape.edges()),
        "circular_edge_count": sum(edge.geom_type == GeomType.CIRCLE for edge in shape.edges()),
        "volume_mm3": sum(abs(float(solid.volume)) for solid in solids),
        "size_mm": [float(bounds.size.X), float(bounds.size.Y), float(bounds.size.Z)],
        "bounds_min_mm": [float(bounds.min.X), float(bounds.min.Y), float(bounds.min.Z)],
        "bounds_max_mm": [float(bounds.max.X), float(bounds.max.Y), float(bounds.max.Z)],
        "interference_volume_mm3": _intersection_volume(solids),
    }


def _relative_error(before: float, after: float) -> float:
    return abs(after - before) / max(abs(before), 1e-12) * 100.0


def inspect_roundtrip(index: int, output_root: Path) -> dict[str, Any]:
    spec = case_spec(index)
    case_id = f"{index:02d}-{spec['family']}-{spec['variant']:02d}"
    step_path = output_root / f"{case_id}.step"
    started = time.perf_counter()
    source = build_case(index)
    before = _metrics(source)
    export_step(source, step_path)
    restored = import_step(step_path)
    after = _metrics(restored)
    size_error = [_relative_error(left, right) for left, right in zip(before["size_mm"], after["size_mm"])]
    volume_error = _relative_error(before["volume_mm3"], after["volume_mm3"])
    interference_error = abs(before["interference_volume_mm3"] - after["interference_volume_mm3"])
    checks = {
        "step_nonempty": step_path.is_file() and step_path.stat().st_size > 1000,
        "source_valid": before["valid"],
        "restored_valid": after["valid"],
        "solid_count_preserved": before["solid_count"] == after["solid_count"],
        "circular_edges_preserved": before["circular_edge_count"] == after["circular_edge_count"],
        "bounds_within_0_02pct": all(error <= 0.02 for error in size_error),
        "volume_within_0_05pct": volume_error <= 0.05,
        "interference_within_0_001mm3": interference_error <= 0.001,
    }
    return {
        "id": case_id,
        "family": spec["family"],
        "variant": spec["variant"],
        "path": str(step_path),
        "passed": all(checks.values()),
        "checks": checks,
        "errors": {
            "size_pct": [round(value, 8) for value in size_error],
            "volume_pct": round(volume_error, 8),
            "interference_mm3": round(interference_error, 8),
        },
        "before": before,
        "after": after,
        "duration_seconds": round(time.perf_counter() - started, 3),
    }


def _markdown(report: dict[str, Any]) -> str:
    lines = [
        "# CAD STEP Round-trip Benchmark",
        "",
        f"- Result: **{report['passed_cases']}/{report['total_cases']} ({report['acceptance_rate_pct']:.2f}%)**",
        f"- Target: {report['target_rate_pct']:.2f}%",
        "",
        "| Case | Family | Result | Volume error | Max bounds error | Interference error |",
        "|---|---|---:|---:|---:|---:|",
    ]
    for case in report["cases"]:
        errors = case.get("errors") or {}
        lines.append(
            f"| {case['id']} | {case['family']} | {'PASS' if case['passed'] else 'FAIL'} | "
            f"{errors.get('volume_pct', math.inf):.6f}% | {max(errors.get('size_pct') or [math.inf]):.6f}% | "
            f"{errors.get('interference_mm3', math.inf):.6f} mm³ |"
        )
    lines.extend(["", "This is a geometry regression contract, not manufacturing certification.", ""])
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate 60 parametric STEP cases and verify export/import invariants")
    parser.add_argument("--output", type=Path, default=STACK_ROOT / "storage" / "benchmarks" / "cad-roundtrip")
    parser.add_argument("--target", type=float, default=95.0)
    args = parser.parse_args()
    run_id = datetime.now().strftime("%Y%m%d-%H%M%S")
    run_root = args.output.resolve() / run_id
    run_root.mkdir(parents=True, exist_ok=False)
    cases = []
    for index in range(CASE_COUNT):
        try:
            result = inspect_roundtrip(index, run_root)
        except Exception as exc:
            spec = case_spec(index)
            result = {"id": f"{index:02d}-{spec['family']}-{spec['variant']:02d}", "family": spec["family"], "passed": False, "error": f"{type(exc).__name__}: {exc}"}
        cases.append(result)
        print(f"[{index + 1:02d}/{CASE_COUNT:02d}] {result['id']} -> {'PASS' if result['passed'] else 'FAIL'}", flush=True)
    passed = sum(bool(case["passed"]) for case in cases)
    rate = passed / len(cases) * 100.0
    report = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "target_rate_pct": args.target,
        "total_cases": len(cases),
        "passed_cases": passed,
        "acceptance_rate_pct": round(rate, 4),
        "passed": rate >= args.target,
        "cases": cases,
    }
    (run_root / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    (run_root / "report.md").write_text(_markdown(report), encoding="utf-8")
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "latest.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    (args.output / "latest.md").write_text(_markdown(report), encoding="utf-8")
    print(json.dumps({key: report[key] for key in ("passed", "passed_cases", "total_cases", "acceptance_rate_pct")}, ensure_ascii=False))
    print(f"Report: {run_root / 'report.md'}")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
