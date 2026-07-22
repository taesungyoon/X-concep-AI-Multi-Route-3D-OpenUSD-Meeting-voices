from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


STACK_ROOT = Path(__file__).resolve().parents[1]


def _value_at(payload: Any, dotted_path: str) -> Any:
    current = payload
    for token in dotted_path.split("."):
        current = current[int(token)] if isinstance(current, list) else current[token]
    return current


def _passes(actual: Any, operator: str, expected: Any) -> bool:
    if operator == "eq":
        return actual == expected
    if operator == "min":
        return float(actual) >= float(expected)
    if operator == "max":
        return float(actual) <= float(expected)
    raise ValueError(f"unsupported operator: {operator}")


def compare(contract: dict[str, Any], stack_root: Path = STACK_ROOT) -> dict[str, Any]:
    results = []
    for source in contract.get("reports") or []:
        path = Path(source["path"])
        if not path.is_absolute():
            path = stack_root / path
        if not path.is_file():
            results.append({"id": source["id"], "path": str(path), "passed": False, "error": "report_missing", "checks": []})
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        checks = []
        for check in source.get("checks") or []:
            try:
                actual = _value_at(payload, check["path"])
                passed = _passes(actual, check["operator"], check["value"])
                checks.append({**check, "actual": actual, "passed": passed})
            except (KeyError, IndexError, TypeError, ValueError) as exc:
                checks.append({**check, "actual": None, "passed": False, "error": f"{type(exc).__name__}: {exc}"})
        results.append({"id": source["id"], "path": str(path), "passed": bool(checks) and all(check["passed"] for check in checks), "checks": checks})
    return {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "contract_id": contract.get("id"),
        "passed": bool(results) and all(result["passed"] for result in results),
        "reports": results,
    }


def _markdown(report: dict[str, Any]) -> str:
    lines = ["# Quality Baseline Diff", "", f"- Result: **{'PASS' if report['passed'] else 'FAIL'}**", "", "| Report | Check | Expected | Actual | Result |", "|---|---|---:|---:|---:|"]
    for source in report["reports"]:
        if not source["checks"]:
            lines.append(f"| {source['id']} | report exists | yes | missing | FAIL |")
        for check in source["checks"]:
            expected = f"{check['operator']} {check['value']}"
            lines.append(f"| {source['id']} | {check['path']} | {expected} | {check.get('actual')} | {'PASS' if check['passed'] else 'FAIL'} |")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Fail when versioned quality report contracts regress")
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=STACK_ROOT / "storage" / "quality-results" / "baseline-diff")
    args = parser.parse_args()
    contract = json.loads(args.contract.resolve().read_text(encoding="utf-8"))
    report = compare(contract)
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    (output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    (output / "report.md").write_text(_markdown(report), encoding="utf-8")
    print(json.dumps({"passed": report["passed"], "reports": {item["id"]: item["passed"] for item in report["reports"]}}, ensure_ascii=False))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
