from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET


STACK_ROOT = Path(__file__).resolve().parents[1]
VALID_PHASES = (1, 2, 3, 4, 6)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _check(check_id: str, passed: bool | None, detail: Any, *, required: bool = True) -> dict[str, Any]:
    return {
        "id": check_id,
        "status": "not_measured" if passed is None else ("passed" if passed else "failed"),
        "required": required,
        "detail": detail,
    }


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as source:
        return [json.loads(line) for line in source if line.strip()]


def _dataset_maps(manifest: dict[str, Any], lock: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    return (
        {item["id"]: item for item in manifest["datasets"]},
        {item["id"]: item for item in lock.get("datasets", [])},
    )


def evaluate_phase1() -> list[dict[str, Any]]:
    env_path = STACK_ROOT / ".env.example"
    compose_path = STACK_ROOT / "docker-compose.yml"
    gitignore_path = STACK_ROOT.parent / ".gitignore"
    env_text = env_path.read_text(encoding="utf-8") if env_path.is_file() else ""
    compose_text = compose_path.read_text(encoding="utf-8") if compose_path.is_file() else ""
    gitignore = gitignore_path.read_text(encoding="utf-8") if gitignore_path.is_file() else ""
    auth_commands = STACK_ROOT / "control-plane-drf" / "api" / "management" / "commands"
    auth_command_files = list(auth_commands.glob("*.py")) if auth_commands.is_dir() else []
    docs_text = "\n".join(
        path.read_text(encoding="utf-8", errors="ignore")
        for path in (STACK_ROOT / "docs").glob("*.md")
    ) if (STACK_ROOT / "docs").is_dir() else ""
    return [
        _check("secrets_ignored", "전체 풀스택/.env" in gitignore and "**/.env" not in gitignore, "tracked template only; runtime .env ignored"),
        _check("default_image_mode_comfyui", "OPENAI_IMAGE_MODE=comfyui" in env_text, "ComfyUI/FLUX is the default image route"),
        _check("openai_key_empty_by_default", "OPENAI_API_KEY=\n" in env_text.replace("\r\n", "\n"), "OpenAI remains opt-in and keyless by default"),
        _check("external_auth_deferred", "AUTH_DB_HOST=\n" in env_text.replace("\r\n", "\n"), "corporate DB host is intentionally unset"),
        _check("mysql_version_pinned", "image: mysql:8.4" in compose_text, "internal MySQL uses a pinned major/minor image"),
        _check("mysql_loopback_only", '127.0.0.1:${MYSQL_HOST_PORT:-3307}:3306' in compose_text, "database port is bound to loopback"),
        _check("mysql_healthcheck", "mysqladmin ping" in compose_text and "service_healthy" in compose_text, "startup is health-gated"),
        _check("auth_schema_command", bool(auth_command_files), [path.name for path in auth_command_files]),
        _check("integration_preflight", (STACK_ROOT / "scripts" / "preflight-integrations.py").is_file(), "external integrations have a no-secret preflight"),
        _check("backup_recovery_documented", "mysqldump" in docs_text.lower() or "backup" in docs_text.lower() or "백업" in docs_text, "MySQL recovery procedure is documented"),
    ]


def evaluate_phase2(manifest_path: Path, dataset_root: Path, manifest: dict[str, Any], lock: dict[str, Any]) -> list[dict[str, Any]]:
    datasets, locked = _dataset_maps(manifest, lock)
    checks = [
        _check("manifest_lock_match", lock.get("manifest_sha256") == sha256_file(manifest_path), {"locked": lock.get("manifest_sha256"), "actual": sha256_file(manifest_path)}),
        _check("license_policy", all(not item.get("auto_download") or not item.get("license_review_required") for item in manifest["datasets"]), "review-required datasets must never auto-download"),
        _check("recognized_licenses", all(bool(item.get("license")) for item in manifest["datasets"]), "every source declares a license or rights note"),
    ]
    for dataset_id, dataset in datasets.items():
        entry = locked.get(dataset_id)
        if not dataset["auto_download"]:
            checks.append(_check(f"{dataset_id}_manual_policy", bool(entry and entry.get("status") == "declared_manual"), dataset.get("manual_reason")))
            continue
        checks.append(_check(f"{dataset_id}_synced", bool(entry and entry.get("status") == "synced"), entry.get("status") if entry else "missing"))
        if not entry:
            continue
        artifact_results = []
        for artifact in entry.get("artifacts", []):
            path = dataset_root / artifact["path"]
            artifact_results.append(path.is_file() and sha256_file(path) == artifact["sha256"])
        checks.append(_check(f"{dataset_id}_artifact_integrity", bool(artifact_results) and all(artifact_results), artifact_results))
        expected_rows = int(dataset["expected_rows"])
        checks.append(_check(f"{dataset_id}_row_count", int(entry.get("row_count", -1)) == expected_rows, {"expected": expected_rows, "actual": entry.get("row_count")}))
        expected_sample = min(int(dataset["sample_sizes"][lock["tier"]]), expected_rows)
        sample = entry.get("sample")
        if expected_sample:
            sample_path = dataset_root / sample["path"] if sample else Path("__missing__")
            checks.append(_check(f"{dataset_id}_sample_integrity", bool(sample and sample.get("count") == expected_sample and sample_path.is_file() and sha256_file(sample_path) == sample["sha256"]), {"expected": expected_sample, "actual": sample.get("count") if sample else None}))
    return checks


def _sample_rows(dataset_id: str, dataset_root: Path, lock_map: dict[str, Any]) -> list[dict[str, Any]]:
    sample = lock_map.get(dataset_id, {}).get("sample")
    if not sample:
        return []
    return _read_jsonl(dataset_root / sample["path"])


def _evaluate_image_results(path: Path, thresholds: dict[str, Any]) -> tuple[dict[str, Any] | None, str | None]:
    if not path.is_file():
        return None, None
    try:
        from PIL import Image
    except ImportError:
        return None, "Pillow is not installed"
    rows = _read_jsonl(path)
    passed = 0
    hashes: list[str] = []
    semantic_scores: list[float] = []
    for row in rows:
        image_path = Path(row["path"])
        if not image_path.is_absolute():
            image_path = path.parent / image_path
        try:
            image_bytes = image_path.read_bytes()
            with Image.open(image_path) as image:
                width, height = image.size
                entropy = float(image.convert("L").entropy())
            basic = (
                width >= thresholds["image_min_width"]
                and height >= thresholds["image_min_height"]
                and len(image_bytes) >= thresholds["image_min_bytes"]
                and entropy >= thresholds["image_min_entropy"]
            )
            passed += int(basic)
            hashes.append(hashlib.sha256(image_bytes).hexdigest())
            if row.get("semantic_score") is not None:
                semantic_scores.append(float(row["semantic_score"]))
        except (OSError, KeyError, ValueError):
            continue
    total = len(rows)
    basic_rate = passed / total * 100 if total else 0.0
    duplicate_count = len(hashes) - len(set(hashes))
    duplicate_rate = duplicate_count / len(hashes) * 100 if hashes else 0.0
    return {
        "count": total,
        "basic_pass_rate_pct": round(basic_rate, 4),
        "exact_duplicate_rate_pct": round(duplicate_rate, 4),
        "semantic_score_pct": round(sum(semantic_scores) / len(semantic_scores) * 100, 4) if semantic_scores else None,
        "semantic_scored_count": len(semantic_scores),
    }, None


def _evaluate_semantic_report(
    manifest: dict[str, Any],
    dataset_root: Path,
    lock_map: dict[str, Any],
    gates: dict[str, Any],
    tier_config: dict[str, Any],
    image_manifest: Path,
    semantic_report: Path,
) -> list[dict[str, Any]]:
    required = bool(tier_config["semantic_score_required"])
    check_ids = ("semantic_report_binding", "semantic_case_coverage", "generated_image_semantic_score")
    if not semantic_report.is_file():
        detail = f"semantic report not found: {semantic_report}"
        return [_check(check_id, False if required else None, detail, required=required) for check_id in check_ids]
    try:
        report = json.loads(semantic_report.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        detail = f"invalid semantic report: {type(exc).__name__}: {exc}"
        return [_check(check_id, False, detail, required=required) for check_id in check_ids]

    evaluator_contract = gates["semantic_evaluator"]
    report_thresholds = report.get("thresholds") if isinstance(report.get("thresholds"), dict) else {}
    toolchain = next(
        (item for item in manifest.get("toolchain_references", []) if item.get("id") == evaluator_contract["toolchain_id"]),
        {},
    )
    geneval_entry = lock_map.get("geneval", {})
    geneval_artifact = (geneval_entry.get("artifacts") or [{}])[0]
    try:
        image_rows = [row for row in _read_jsonl(image_manifest) if row.get("dataset") == "geneval"]
    except (OSError, ValueError, KeyError):
        image_rows = []
    image_by_index = {int(row["row_index"]): row for row in image_rows if row.get("row_index") is not None}
    cases = report.get("cases") if isinstance(report.get("cases"), list) else []
    case_indices = [int(case["row_index"]) for case in cases if case.get("row_index") is not None]
    selected_indices = set((geneval_entry.get("sample") or {}).get("selected_indices") or [])
    case_bindings = []
    for case in cases:
        try:
            row_index = int(case["row_index"])
            image_row = image_by_index[row_index]
            image_path = Path(image_row["path"])
            if not image_path.is_absolute():
                image_path = image_manifest.parent / image_path
            case_bindings.append(
                case.get("dataset") == "geneval"
                and row_index in selected_indices
                and case.get("prompt_sha256") == image_row.get("prompt_sha256")
                and image_path.is_file()
                and case.get("image_sha256") == sha256_file(image_path)
            )
        except (KeyError, OSError, TypeError, ValueError):
            case_bindings.append(False)
    binding_detail = {
        "evaluator": report.get("evaluator"),
        "model_id": report.get("model_id"),
        "model_revision": report.get("model_revision"),
        "dataset_revision": report.get("dataset_revision"),
        "case_count": report.get("case_count"),
    }
    binding_ok = (
        bool(toolchain)
        and report.get("evaluator") == evaluator_contract["evaluator"]
        and report.get("official_geneval_score") is evaluator_contract["official_geneval_score"]
        and report.get("model_id") == toolchain.get("model_id")
        and report.get("model_revision") == toolchain.get("revision")
        and report.get("model_license") == toolchain.get("license")
        and float(report_thresholds.get("detection", -1)) == float(evaluator_contract["detection_threshold"])
        and float(report_thresholds.get("nms_iou", -1)) == float(evaluator_contract["nms_iou_threshold"])
        and float(report_thresholds.get("text", -1)) == float(evaluator_contract["text_threshold"])
        and report.get("dataset_revision") == geneval_entry.get("revision")
        and report.get("dataset_source_sha256") == geneval_artifact.get("sha256")
        and image_manifest.is_file()
        and report.get("image_manifest_sha256") == sha256_file(image_manifest)
        and len(image_by_index) == len(image_rows)
        and len(case_indices) == len(set(case_indices)) == len(image_rows)
        and set(case_indices) == set(image_by_index)
        and int(report.get("case_count", -1)) == len(cases)
        and int(report.get("correct_count", -1)) == sum(bool(case.get("correct")) for case in cases)
        and bool(case_bindings)
        and all(case_bindings)
    )
    required_tags = set(gates["thresholds"]["geneval_required_tags"])
    task_scores = report.get("task_scores") if isinstance(report.get("task_scores"), dict) else {}
    covered_tags = {tag for tag, value in task_scores.items() if isinstance(value, dict) and int(value.get("count", 0)) > 0}
    minimum_cases = int(tier_config["semantic_min_result_count"])
    case_count = int(report.get("case_count", 0))
    coverage_ok = case_count >= minimum_cases and required_tags.issubset(covered_tags)
    coverage_detail = {
        "case_count": case_count,
        "minimum_case_count": minimum_cases,
        "required_tags": sorted(required_tags),
        "covered_tags": sorted(covered_tags),
    }
    score = float(report.get("overall_score_pct", 0))
    target = float(gates["thresholds"]["image_semantic_score_pct"])
    score_ok = score >= target
    score_detail = {
        "score_pct": score,
        "target_pct": target,
        "official_geneval_score": report.get("official_geneval_score"),
        "note": "portable GenEval-compatible score; not the official GenEval metric",
    }
    return [
        _check("semantic_report_binding", binding_ok, binding_detail, required=required),
        _check("semantic_case_coverage", coverage_ok, coverage_detail, required=required),
        _check("generated_image_semantic_score", score_ok, score_detail, required=required),
    ]


def evaluate_phase3(
    manifest: dict[str, Any],
    dataset_root: Path,
    lock: dict[str, Any],
    gates: dict[str, Any],
    tier_config: dict[str, Any],
    image_manifest: Path,
    semantic_report: Path,
) -> list[dict[str, Any]]:
    thresholds = gates["thresholds"]
    lock_map = {item["id"]: item for item in lock.get("datasets", [])}
    parti = _sample_rows("parti-prompts", dataset_root, lock_map)
    geneval = _sample_rows("geneval", dataset_root, lock_map)
    categories = {str(row.get("category", "")).strip() for row in parti if str(row.get("category", "")).strip()}
    challenges = {str(row.get("challenge", "")).strip() for row in parti if str(row.get("challenge", "")).strip()}
    tags = {str(row.get("tag", "")).strip() for row in geneval if str(row.get("tag", "")).strip()}
    required_tags = set(thresholds["geneval_required_tags"])
    checks = [
        _check("parti_sample_available", bool(parti), len(parti)),
        _check("parti_category_coverage", len(categories) >= thresholds["parti_min_categories"], sorted(categories)),
        _check("parti_challenge_coverage", len(challenges) >= thresholds["parti_min_challenges"], sorted(challenges)),
        _check("geneval_sample_available", bool(geneval), len(geneval)),
        _check("geneval_task_coverage", required_tags.issubset(tags), {"required": sorted(required_tags), "actual": sorted(tags)}),
    ]
    metrics, error = _evaluate_image_results(image_manifest, thresholds)
    results_required = bool(tier_config["image_results_required"])
    if metrics is None:
        checks.append(_check("generated_image_basic_quality", None if not results_required else False, error or f"result manifest not found: {image_manifest}", required=results_required))
    else:
        basic_ok = (
            metrics["count"] >= int(tier_config["image_min_result_count"])
            and metrics["basic_pass_rate_pct"] >= thresholds["image_basic_pass_rate_pct"]
            and metrics["exact_duplicate_rate_pct"] <= thresholds["image_max_exact_duplicate_rate_pct"]
        )
        checks.append(_check("generated_image_basic_quality", basic_ok, metrics, required=results_required))
    checks.extend(_evaluate_semantic_report(manifest, dataset_root, lock_map, gates, tier_config, image_manifest, semantic_report))
    return checks


def evaluate_phase4(
    manifest: dict[str, Any],
    lock: dict[str, Any],
    gates: dict[str, Any],
    tier_config: dict[str, Any],
    benchmark_path: Path,
    public_cad_report_path: Path,
) -> list[dict[str, Any]]:
    datasets, locked = _dataset_maps(manifest, lock)
    checks = [
        _check("native_cad_benchmark_adapter", (STACK_ROOT / "scripts" / "benchmark-native-cad.py").is_file(), "OpenSCAD/Blender 25-case adapter"),
        _check("nist_public_cad_declared", "nist-pmi-step" in datasets and locked.get("nist-pmi-step", {}).get("status") == "synced", datasets.get("nist-pmi-step", {}).get("revision")),
        _check("abc_rights_guard", bool(datasets.get("abc-cad", {}).get("license_review_required") and locked.get("abc-cad", {}).get("status") == "declared_manual"), datasets.get("abc-cad", {}).get("license")),
        _check("sketchgraphs_rights_guard", bool(datasets.get("sketchgraphs", {}).get("license_review_required") and locked.get("sketchgraphs", {}).get("status") == "declared_manual"), datasets.get("sketchgraphs", {}).get("license")),
    ]
    benchmark_required = bool(tier_config["native_cad_benchmark_required"])
    if benchmark_path.is_file():
        report = json.loads(benchmark_path.read_text(encoding="utf-8"))
        target = float(gates["thresholds"]["native_cad_acceptance_rate_pct"])
        healthy_cases = all(
            case.get("passed")
            or not case.get("checks")
            or (case["checks"].get("finite_geometry", True) and case["checks"].get("faces_present", True))
            for case in report.get("cases", [])
        )
        checks.append(_check("native_cad_acceptance", float(report.get("acceptance_rate_pct", 0)) >= target and healthy_cases, {"rate_pct": report.get("acceptance_rate_pct"), "target_pct": target, "cases": report.get("total_cases")}, required=benchmark_required))
    else:
        checks.append(_check("native_cad_acceptance", False if benchmark_required else None, f"benchmark not found: {benchmark_path}", required=benchmark_required))
    public_required = bool(tier_config["cad_public_data_required"])
    nist_entry = locked.get("nist-pmi-step", {})
    nist_sample = nist_entry.get("sample") or {}
    if public_cad_report_path.is_file():
        public_report = json.loads(public_cad_report_path.read_text(encoding="utf-8"))
        target = float(gates["thresholds"]["public_cad_acceptance_rate_pct"])
        public_ok = (
            public_report.get("lock_tier") == lock.get("tier")
            and public_report.get("source_archive_sha256") == (nist_entry.get("artifacts") or [{}])[0].get("sha256")
            and public_report.get("sample_sha256") == nist_sample.get("sha256")
            and int(public_report.get("total_cases", 0)) == int(nist_sample.get("count", -1))
            and float(public_report.get("acceptance_rate_pct", 0)) >= target
        )
        checks.append(_check("nist_public_cad_acceptance", public_ok, {"rate_pct": public_report.get("acceptance_rate_pct"), "target_pct": target, "cases": public_report.get("total_cases"), "lock_tier": public_report.get("lock_tier")}, required=public_required))
    else:
        checks.append(_check("nist_public_cad_acceptance", False if public_required else None, f"benchmark not found: {public_cad_report_path}", required=public_required))
    return checks


def evaluate_phase6(dataset_root: Path, lock: dict[str, Any], gates: dict[str, Any], tier_config: dict[str, Any]) -> list[dict[str, Any]]:
    thresholds = gates["thresholds"]
    lock_map = {item["id"]: item for item in lock.get("datasets", [])}
    entry = lock_map.get("usd-wg-primvar", {})
    paths = [dataset_root / artifact["path"] for artifact in entry.get("artifacts", [])]
    checks = [_check("usd_reference_asset_available", bool(paths) and all(path.is_file() for path in paths), [str(path) for path in paths])]
    opened = 0
    pxr_error: str | None = None
    try:
        from pxr import Usd
        for path in paths:
            stage = Usd.Stage.Open(str(path))
            if stage is not None and any(True for _ in stage.Traverse()):
                opened += 1
    except Exception as exc:
        pxr_error = f"{type(exc).__name__}: {exc}"
    pxr_required = bool(tier_config["pxr_required"])
    open_rate = opened / len(paths) * 100 if paths else 0.0
    if pxr_error:
        checks.append(_check("pxr_stage_open", False if pxr_required else None, pxr_error, required=pxr_required))
    else:
        checks.append(_check("pxr_stage_open", open_rate >= thresholds["usd_stage_open_rate_pct"], {"opened": opened, "total": len(paths), "rate_pct": open_rate}, required=pxr_required))
    checker = shutil.which("usdchecker")
    checker_required = bool(tier_config["usdchecker_required"])
    if checker:
        results = []
        for path in paths:
            completed = subprocess.run([checker, str(path)], capture_output=True, text=True, timeout=60)
            results.append({"path": str(path), "returncode": completed.returncode, "engine": "usdchecker-cli"})
        checks.append(_check("usdchecker_compliance", bool(results) and all(item["returncode"] == 0 for item in results), results, required=checker_required))
    else:
        try:
            from pxr import Usd, UsdValidation

            validators = UsdValidation.ValidationRegistry().GetOrLoadAllValidators()
            context = UsdValidation.ValidationContext(validators)
            results = []
            for path in paths:
                stage = Usd.Stage.Open(str(path))
                errors = context.Validate(stage) if stage is not None else []
                results.append(
                    {
                        "path": str(path),
                        "engine": "UsdValidation",
                        "validator_count": len(validators),
                        "errors": [
                            {"name": str(error.GetName()), "message": str(error.GetMessage())}
                            for error in errors
                        ],
                    }
                )
            checks.append(_check("usdchecker_compliance", bool(results) and all(not item["errors"] for item in results), results, required=checker_required))
        except Exception as exc:
            checks.append(_check("usdchecker_compliance", False if checker_required else None, f"usdchecker CLI and UsdValidation unavailable: {type(exc).__name__}: {exc}", required=checker_required))
    checks.append(_check("openusd_exporter_tests", (STACK_ROOT / "python-worker" / "tests" / "test_security_openusd.py").is_file(), "project exporter security/composition regression tests exist"))
    return checks


def summarize_phase(phase: int, checks: list[dict[str, Any]], tier_config: dict[str, Any]) -> dict[str, Any]:
    required = [item for item in checks if item["required"]]
    passed_count = sum(item["status"] == "passed" for item in required)
    score = passed_count / len(required) * 100 if required else 100.0
    minimum = float(tier_config["phase_minimum_score_pct"][str(phase)])
    critical = set(tier_config.get("phase1_critical_checks", [])) if phase == 1 else set()
    critical_failed = [item["id"] for item in checks if item["id"] in critical and item["status"] != "passed"]
    passed = score >= minimum and not critical_failed
    return {
        "phase": phase,
        "passed": passed,
        "score_pct": round(score, 4),
        "minimum_score_pct": minimum,
        "required_checks": len(required),
        "passed_required_checks": passed_count,
        "critical_failures": critical_failed,
        "checks": checks,
    }


def _markdown(report: dict[str, Any]) -> str:
    lines = [
        "# XconcepAI Quality Program",
        "",
        f"- Tier: **{report['tier']}**",
        f"- Readiness result: **{'PASS' if report['passed'] else 'FAIL'}**",
        f"- Dataset revision lock: `{report['dataset_lock_sha256']}`",
        f"- Seed: `{report['seed']}`",
        "",
        "| Phase | Result | Required score | Gate |",
        "|---:|---:|---:|---:|",
    ]
    for phase in report["phases"]:
        lines.append(f"| {phase['phase']} | {'PASS' if phase['passed'] else 'FAIL'} | {phase['score_pct']:.2f}% | {phase['minimum_score_pct']:.2f}% |")
    for phase in report["phases"]:
        lines.extend(["", f"## Phase {phase['phase']}", "", "| Check | Required | Status |", "|---|---:|---:|"])
        for check in phase["checks"]:
            lines.append(f"| {check['id']} | {'yes' if check['required'] else 'no'} | {check['status']} |")
    lines.extend([
        "",
        "`not_measured` evidence is never counted as a pass. Smoke validates reproducibility/readiness; standard/full require progressively more live evidence.",
        "The 95% CAD gate is an automated acceptance contract, not manufacturing approval.",
        "",
    ])
    return "\n".join(lines)


def _junit(report: dict[str, Any]) -> str:
    tests = sum(len(phase["checks"]) for phase in report["phases"])
    failures = sum(check["status"] == "failed" and check["required"] for phase in report["phases"] for check in phase["checks"])
    suite = ET.Element("testsuite", name="xconcep-quality", tests=str(tests), failures=str(failures))
    for phase in report["phases"]:
        for check in phase["checks"]:
            case = ET.SubElement(suite, "testcase", classname=f"phase{phase['phase']}", name=check["id"])
            if check["status"] == "failed" and check["required"]:
                failure = ET.SubElement(case, "failure", message=str(check["detail"]))
                failure.text = json.dumps(check["detail"], ensure_ascii=False)
            elif check["status"] == "not_measured":
                ET.SubElement(case, "skipped", message=str(check["detail"]))
    return ET.tostring(suite, encoding="unicode")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run phase 1,2,3,4,6 quality gates")
    parser.add_argument("--tier", choices=("smoke", "standard", "full"), default="smoke")
    parser.add_argument("--phases", default="1,2,3,4,6")
    parser.add_argument("--manifest", type=Path, default=STACK_ROOT / "quality" / "datasets.json")
    parser.add_argument("--gates", type=Path, default=STACK_ROOT / "quality" / "gates.json")
    parser.add_argument("--dataset-root", type=Path, default=STACK_ROOT / "storage" / "quality-datasets")
    parser.add_argument("--image-manifest", type=Path, default=STACK_ROOT / "storage" / "quality-results" / "images" / "manifest.jsonl")
    parser.add_argument("--semantic-report", type=Path, default=STACK_ROOT / "storage" / "quality-results" / "images" / "geneval-semantic.json")
    parser.add_argument("--native-cad-report", type=Path, default=STACK_ROOT / "storage" / "benchmarks" / "native-cad" / "latest.json")
    parser.add_argument("--public-cad-report", type=Path, default=STACK_ROOT / "storage" / "benchmarks" / "public-cad-nist" / "latest.json")
    parser.add_argument("--output", type=Path, default=STACK_ROOT / "storage" / "quality-program")
    args = parser.parse_args()

    selected = tuple(int(value.strip()) for value in args.phases.split(",") if value.strip())
    if not selected or any(value not in VALID_PHASES for value in selected):
        raise SystemExit(f"Phases must be selected from {VALID_PHASES}")
    manifest_path = args.manifest.resolve()
    gates_path = args.gates.resolve()
    dataset_root = args.dataset_root.resolve()
    lock_path = dataset_root / "quality-datasets.lock.json"
    if not lock_path.is_file():
        raise SystemExit(f"Dataset lock missing. Run sync-quality-datasets.py first: {lock_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    gates = json.loads(gates_path.read_text(encoding="utf-8"))
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    if lock.get("tier") != args.tier:
        raise SystemExit(f"Dataset lock tier is {lock.get('tier')}; requested {args.tier}. Re-run dataset sync.")
    tier_config = gates["tiers"][args.tier]

    phase_checks: dict[int, list[dict[str, Any]]] = {}
    if 1 in selected:
        phase_checks[1] = evaluate_phase1()
    if 2 in selected:
        phase_checks[2] = evaluate_phase2(manifest_path, dataset_root, manifest, lock)
    if 3 in selected:
        phase_checks[3] = evaluate_phase3(manifest, dataset_root, lock, gates, tier_config, args.image_manifest.resolve(), args.semantic_report.resolve())
    if 4 in selected:
        phase_checks[4] = evaluate_phase4(manifest, lock, gates, tier_config, args.native_cad_report.resolve(), args.public_cad_report.resolve())
    if 6 in selected:
        phase_checks[6] = evaluate_phase6(dataset_root, lock, gates, tier_config)
    phases = [summarize_phase(phase, phase_checks[phase], tier_config) for phase in selected]

    output_root = args.output.resolve()
    latest_path = output_root / "latest.json"
    previous = json.loads(latest_path.read_text(encoding="utf-8")) if latest_path.is_file() else None
    run_id = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    report = {
        "schema_version": 1,
        "run_id": run_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "tier": args.tier,
        "seed": lock["seed"],
        "dataset_lock_sha256": sha256_file(lock_path),
        "selected_phases": list(selected),
        "passed": all(phase["passed"] for phase in phases),
        "phases": phases,
        "trend": {
            "previous_run_id": previous.get("run_id") if previous else None,
            "phase_score_delta_pct": {
                str(phase["phase"]): round(phase["score_pct"] - next((old["score_pct"] for old in previous.get("phases", []) if old["phase"] == phase["phase"]), phase["score_pct"]), 4) if previous else 0.0
                for phase in phases
            },
        },
        "limitations": [
            "Smoke tier measures reproducibility and evaluator readiness; it does not claim live image semantic accuracy.",
            "ABC and SketchGraphs full corpora remain opt-in because of size and/or rights review.",
            "CAD 95% is an automated software acceptance rate, not dimensional metrology or manufacturing approval.",
        ],
    }
    run_root = output_root / run_id
    run_root.mkdir(parents=True, exist_ok=False)
    if previous:
        (run_root / "previous-report.json").write_text(
            json.dumps(previous, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    json_text = json.dumps(report, ensure_ascii=False, indent=2)
    markdown = _markdown(report)
    (run_root / "report.json").write_text(json_text, encoding="utf-8")
    (run_root / "report.md").write_text(markdown, encoding="utf-8")
    (run_root / "junit.xml").write_text(_junit(report), encoding="utf-8")
    output_root.mkdir(parents=True, exist_ok=True)
    latest_path.write_text(json_text, encoding="utf-8")
    (output_root / "latest.md").write_text(markdown, encoding="utf-8")
    print(json.dumps({"passed": report["passed"], "tier": args.tier, "phases": [{"phase": item["phase"], "score_pct": item["score_pct"], "passed": item["passed"]} for item in phases]}, ensure_ascii=False))
    print(f"Report: {run_root / 'report.md'}")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
