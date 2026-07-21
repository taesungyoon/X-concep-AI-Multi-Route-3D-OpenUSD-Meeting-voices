from __future__ import annotations

import argparse
import hashlib
import json
import math
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from build123d import Compound
from OCP.IFSelect import IFSelect_RetDone
from OCP.STEPControl import STEPControl_Reader


STACK_ROOT = Path(__file__).resolve().parents[1]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _import_step_geometry(path: Path) -> Compound:
    """Load geometry without XCAF name/color transfer, which is irrelevant to this benchmark."""
    reader = STEPControl_Reader()
    status = reader.ReadFile(str(path))
    if status != IFSelect_RetDone:
        raise ValueError(f"STEP read failed: {status}")
    transferred = reader.TransferRoots()
    if transferred < 1:
        raise ValueError("STEP contains no transferable roots")
    raw_shape = reader.OneShape()
    if raw_shape.IsNull():
        raise ValueError("STEP transfer produced a null shape")
    return Compound(raw_shape)


def _inspect_case(dataset_root: Path, row: dict[str, Any]) -> dict[str, Any]:
    path = dataset_root / row["artifact_path"]
    started = time.perf_counter()
    result: dict[str, Any] = {
        "id": path.stem,
        "path": str(path),
        "source_sha256": row["sha256"],
        "representation": "tessellated" if "-tg" in path.stem.lower() else "brep",
    }
    try:
        header = path.read_text(encoding="latin-1", errors="ignore")[:100_000]
        shape = _import_step_geometry(path)
        bounds = shape.bounding_box()
        size = [float(bounds.size.X), float(bounds.size.Y), float(bounds.size.Z)]
        minimum = [float(bounds.min.X), float(bounds.min.Y), float(bounds.min.Z)]
        maximum = [float(bounds.max.X), float(bounds.max.Y), float(bounds.max.Z)]
        solid_count = len(shape.solids())
        face_count = len(shape.faces())
        edge_count = len(shape.edges())
        compound_volume = float(shape.volume)
        solid_volumes = [float(solid.volume) for solid in shape.solids()]
        volume = sum(abs(value) for value in solid_volumes)
        is_tessellated = result["representation"] == "tessellated"
        checks = {
            "checksum": sha256_file(path) == row["sha256"],
            "step_part21_header": "ISO-10303-21" in header and "FILE_SCHEMA" in header,
            "ap242_schema": "AP242" in header or "MANAGED_MODEL_BASED_3D_ENGINEERING" in header,
            "representation_valid": ("COMPLEX_TRIANGULATED_FACE" in header) if is_tessellated else bool(shape.is_valid),
            "geometry_present": face_count > 0 and (is_tessellated or edge_count > 0),
            "finite_bounds": all(math.isfinite(value) for value in minimum + maximum + size),
            "positive_extents": all(value > 0 for value in size),
            "solid_or_tessellated": is_tessellated or solid_count > 0,
            "positive_volume_or_tessellated": is_tessellated or (math.isfinite(volume) and volume > 0),
        }
        result.update(
            {
                "passed": all(checks.values()),
                "checks": checks,
                "metrics": {
                    "solid_count": solid_count,
                    "face_count": face_count,
                    "edge_count": edge_count,
                    "volume_mm3": volume,
                    "compound_volume_mm3": compound_volume,
                    "solid_volumes_mm3": solid_volumes,
                    "bounds_min_mm": minimum,
                    "bounds_max_mm": maximum,
                    "size_mm": size,
                },
            }
        )
    except Exception as exc:
        result.update({"passed": False, "error": f"{type(exc).__name__}: {exc}"})
    result["duration_seconds"] = round(time.perf_counter() - started, 3)
    return result


def _inspect_case_isolated(dataset_root: Path, row: dict[str, Any], timeout_seconds: int) -> dict[str, Any]:
    """Keep one malformed/native-crashing STEP from aborting the whole corpus run."""
    started = time.perf_counter()
    command = [
        sys.executable,
        str(Path(__file__).resolve()),
        "--dataset-root",
        str(dataset_root),
        "--worker-row-json",
        json.dumps(row, ensure_ascii=True, separators=(",", ":")),
    ]
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        return {
            "id": Path(row["artifact_path"]).stem,
            "path": str(dataset_root / row["artifact_path"]),
            "source_sha256": row["sha256"],
            "representation": "tessellated" if "-tg" in Path(row["artifact_path"]).stem.lower() else "brep",
            "passed": False,
            "error": f"worker_timeout_after_{timeout_seconds}s",
            "worker_stderr": (exc.stderr or "")[-2000:] if isinstance(exc.stderr, str) else "",
            "duration_seconds": round(time.perf_counter() - started, 3),
        }
    marker = "CAD_CASE_JSON="
    payload = next((line[len(marker):] for line in reversed(completed.stdout.splitlines()) if line.startswith(marker)), None)
    if completed.returncode == 0 and payload:
        return json.loads(payload)
    return {
        "id": Path(row["artifact_path"]).stem,
        "path": str(dataset_root / row["artifact_path"]),
        "source_sha256": row["sha256"],
        "representation": "tessellated" if "-tg" in Path(row["artifact_path"]).stem.lower() else "brep",
        "passed": False,
        "error": f"worker_exit_{completed.returncode}",
        "worker_stdout": completed.stdout[-2000:],
        "worker_stderr": completed.stderr[-2000:],
        "duration_seconds": round(time.perf_counter() - started, 3),
    }


def _markdown(report: dict[str, Any]) -> str:
    lines = [
        "# NIST PMI STEP Public CAD Benchmark",
        "",
        f"- Result: **{report['passed_cases']}/{report['total_cases']} ({report['acceptance_rate_pct']:.2f}%)**",
        f"- Target: {report['target_rate_pct']:.2f}%",
        f"- Dataset: `{report['dataset_revision']}`",
        f"- Archive SHA-256: `{report['source_archive_sha256']}`",
        "",
        "| Case | Representation | Result | Solids | Faces | Size (mm) | Time (s) |",
        "|---|---|---:|---:|---:|---|---:|",
    ]
    for case in report["cases"]:
        metrics = case.get("metrics") or {}
        size = " × ".join(f"{value:.3f}" for value in metrics.get("size_mm", [])) or "-"
        lines.append(
            f"| {case['id']} | {case['representation']} | {'PASS' if case['passed'] else 'FAIL'} | "
            f"{metrics.get('solid_count', '-')} | {metrics.get('face_count', '-')} | {size} | {case['duration_seconds']:.3f} |"
        )
    lines.extend(["", "NIST test data is used for geometry/interoperability regression, not manufacturing certification.", ""])
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate the pinned NIST PMI STEP public CAD sample")
    parser.add_argument("--dataset-root", type=Path, default=STACK_ROOT / "storage" / "quality-datasets")
    parser.add_argument("--output", type=Path, default=STACK_ROOT / "storage" / "benchmarks" / "public-cad-nist")
    parser.add_argument("--target", type=float, default=100.0)
    parser.add_argument("--case-timeout-seconds", type=int, default=120)
    parser.add_argument("--worker-row-json", help=argparse.SUPPRESS)
    args = parser.parse_args()
    dataset_root = args.dataset_root.resolve()
    if args.worker_row_json:
        worker_result = _inspect_case(dataset_root, json.loads(args.worker_row_json))
        print("CAD_CASE_JSON=" + json.dumps(worker_result, ensure_ascii=True, separators=(",", ":")))
        return 0
    lock_path = dataset_root / "quality-datasets.lock.json"
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    entry = next(item for item in lock["datasets"] if item["id"] == "nist-pmi-step")
    sample = entry.get("sample")
    if not sample:
        raise SystemExit("NIST sample is missing from the dataset lock")
    rows = [json.loads(line) for line in (dataset_root / sample["path"]).read_text(encoding="utf-8").splitlines() if line.strip()]
    cases = []
    for index, row in enumerate(rows, start=1):
        case = _inspect_case_isolated(dataset_root, row, args.case_timeout_seconds)
        cases.append(case)
        print(f"[{index:02d}/{len(rows):02d}] {case['id']}: {'PASS' if case['passed'] else 'FAIL'}", flush=True)
    passed_cases = sum(case["passed"] for case in cases)
    rate = passed_cases / len(cases) * 100 if cases else 0.0
    report = {
        "benchmark_version": "1.0",
        "reader_mode": "OpenCascade STEPControl geometry-only",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "lock_tier": lock["tier"],
        "seed": lock["seed"],
        "dataset_revision": entry["revision"],
        "source_archive_sha256": entry["artifacts"][0]["sha256"],
        "sample_sha256": sample["sha256"],
        "target_rate_pct": args.target,
        "total_cases": len(cases),
        "passed_cases": passed_cases,
        "acceptance_rate_pct": round(rate, 4),
        "passed": rate >= args.target,
        "cases": cases,
    }
    run_id = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    output_root = args.output.resolve()
    run_root = output_root / run_id
    run_root.mkdir(parents=True, exist_ok=False)
    json_text = json.dumps(report, ensure_ascii=False, indent=2)
    markdown = _markdown(report)
    (run_root / "report.json").write_text(json_text, encoding="utf-8")
    (run_root / "report.md").write_text(markdown, encoding="utf-8")
    output_root.mkdir(parents=True, exist_ok=True)
    (output_root / "latest.json").write_text(json_text, encoding="utf-8")
    (output_root / "latest.md").write_text(markdown, encoding="utf-8")
    print(json.dumps({"passed": report["passed"], "passed_cases": passed_cases, "total_cases": len(cases), "acceptance_rate_pct": report["acceptance_rate_pct"]}))
    print(f"Report: {run_root / 'report.md'}")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
