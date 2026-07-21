from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import shutil
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from pathlib import PurePosixPath
from typing import Any
from zipfile import ZipFile


STACK_ROOT = Path(__file__).resolve().parents[1]
TIER_ORDER = {"smoke": 0, "standard": 1, "full": 2}


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def deterministic_indices(total: int, count: int, seed: int, dataset_id: str) -> list[int]:
    count = min(max(count, 0), total)
    ranked = sorted(
        range(total),
        key=lambda index: hashlib.sha256(f"{seed}:{dataset_id}:{index}".encode("utf-8")).digest(),
    )
    return sorted(ranked[:count])


def _validate_url(url: str, manifest: dict[str, Any]) -> None:
    parsed = urllib.parse.urlparse(url)
    policy = manifest["policy"]
    if parsed.scheme not in set(policy["allowed_schemes"]):
        raise ValueError(f"Blocked URL scheme: {parsed.scheme}")
    if parsed.hostname not in set(policy["allowed_hosts"]):
        raise ValueError(f"Blocked URL host: {parsed.hostname}")


def _download(url: str, retries: int = 3) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "XconcepAI-Quality/1.0"})
    last_error: Exception | None = None
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                return response.read()
        except (OSError, urllib.error.URLError) as exc:
            last_error = exc
            if attempt + 1 < retries:
                time.sleep(1 + attempt)
    raise RuntimeError(f"Download failed after {retries} attempts: {url}") from last_error


def _safe_zip_records(
    dataset: dict[str, Any],
    archive_path: Path,
    dataset_root: Path,
    output_root: Path,
) -> list[dict[str, Any]]:
    pattern = re.compile(str(dataset["archive_member_pattern"]))
    max_member = int(dataset.get("archive_max_member_bytes", 10_000_000))
    max_total = int(dataset.get("archive_max_total_bytes", 100_000_000))
    extracted_root = dataset_root / "extracted"
    records: list[dict[str, Any]] = []
    total_bytes = 0
    with ZipFile(archive_path) as archive:
        members = sorted(
            (info for info in archive.infolist() if not info.is_dir() and pattern.fullmatch(info.filename)),
            key=lambda info: info.filename,
        )
        for row_index, info in enumerate(members):
            member = PurePosixPath(info.filename)
            if member.is_absolute() or ".." in member.parts or not member.parts:
                raise RuntimeError(f"Unsafe ZIP member: {info.filename}")
            if info.file_size <= 0 or info.file_size > max_member:
                raise RuntimeError(f"ZIP member size rejected: {info.filename} ({info.file_size})")
            total_bytes += info.file_size
            if total_bytes > max_total:
                raise RuntimeError(f"ZIP extraction limit exceeded: {total_bytes} > {max_total}")
            destination = extracted_root.joinpath(*member.parts)
            destination.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(info) as source, destination.open("wb") as target:
                shutil.copyfileobj(source, target, length=1024 * 1024)
            records.append(
                {
                    "row_index": row_index,
                    "name": destination.name,
                    "artifact_path": destination.relative_to(output_root).as_posix(),
                    "bytes": destination.stat().st_size,
                    "sha256": sha256_file(destination),
                }
            )
    return records


def _read_records(
    dataset: dict[str, Any],
    artifact_paths: list[Path],
    dataset_root: Path,
    output_root: Path,
) -> list[dict[str, Any]]:
    record_format = dataset["record_format"]
    if record_format == "files":
        return []
    if record_format == "zip":
        return _safe_zip_records(dataset, artifact_paths[0], dataset_root, output_root)
    source = artifact_paths[0]
    if record_format == "tsv":
        with source.open("r", encoding="utf-8-sig", newline="") as stream:
            rows = list(csv.DictReader(stream, delimiter="\t"))
        return [
            {
                "row_index": index,
                "prompt": row.get("Prompt", ""),
                "category": row.get("Category", ""),
                "challenge": row.get("Challenge", ""),
                "note": row.get("Note", ""),
            }
            for index, row in enumerate(rows)
        ]
    if record_format == "jsonl":
        rows = []
        with source.open("r", encoding="utf-8") as stream:
            for index, line in enumerate(stream):
                if line.strip():
                    row = json.loads(line)
                    row["row_index"] = index
                    rows.append(row)
        return rows
    raise ValueError(f"Unsupported record format: {record_format}")


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as target:
        for row in rows:
            target.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def sync(manifest_path: Path, output_root: Path, tier: str, seed: int, offline: bool) -> dict[str, Any]:
    manifest_bytes = manifest_path.read_bytes()
    manifest = json.loads(manifest_bytes)
    output_root.mkdir(parents=True, exist_ok=True)
    lock_entries: list[dict[str, Any]] = []

    for dataset in manifest["datasets"]:
        entry: dict[str, Any] = {
            "id": dataset["id"],
            "revision": dataset["revision"],
            "license": dataset["license"],
            "auto_download": dataset["auto_download"],
            "license_review_required": dataset["license_review_required"],
        }
        if not dataset["auto_download"]:
            entry.update({"status": "declared_manual", "reason": dataset.get("manual_reason", "manual")})
            lock_entries.append(entry)
            continue
        if dataset["license_review_required"]:
            raise RuntimeError(f"Policy violation: {dataset['id']} cannot be auto-downloaded before license review")

        dataset_root = output_root / "source" / dataset["id"]
        dataset_root.mkdir(parents=True, exist_ok=True)
        artifact_paths: list[Path] = []
        artifacts: list[dict[str, Any]] = []
        for artifact in dataset["artifacts"]:
            _validate_url(artifact["url"], manifest)
            destination = dataset_root / artifact["dest"]
            if offline:
                if not destination.is_file():
                    raise FileNotFoundError(f"Offline artifact missing: {destination}")
            else:
                data = _download(artifact["url"])
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(data)
            artifact_paths.append(destination)
            actual_sha256 = sha256_file(destination)
            expected_sha256 = artifact.get("sha256")
            if expected_sha256 and actual_sha256.lower() != str(expected_sha256).lower():
                raise RuntimeError(
                    f"{dataset['id']} checksum mismatch for {artifact['dest']}: "
                    f"expected {expected_sha256}, got {actual_sha256}"
                )
            artifacts.append(
                {
                    "path": destination.relative_to(output_root).as_posix(),
                    "url": artifact["url"],
                    "bytes": destination.stat().st_size,
                    "sha256": actual_sha256,
                    "expected_sha256": expected_sha256,
                }
            )

        records = _read_records(dataset, artifact_paths, dataset_root, output_root)
        expected_rows = int(dataset["expected_rows"])
        if dataset["record_format"] != "files" and len(records) != expected_rows:
            raise RuntimeError(f"{dataset['id']} row mismatch: expected {expected_rows}, got {len(records)}")
        sample_count = min(int(dataset["sample_sizes"][tier]), len(records))
        selected = deterministic_indices(len(records), sample_count, seed, dataset["id"])
        sample_rows = [records[index] for index in selected]
        sample_path: Path | None = None
        sample_meta: dict[str, Any] | None = None
        if records:
            sample_path = output_root / "samples" / f"{dataset['id']}-{tier}.jsonl"
            _write_jsonl(sample_path, sample_rows)
            sample_meta = {
                "path": sample_path.relative_to(output_root).as_posix(),
                "count": len(sample_rows),
                "sha256": sha256_file(sample_path),
                "selected_indices": selected,
            }
        entry.update(
            {
                "status": "synced",
                "row_count": len(records),
                "artifacts": artifacts,
                "sample": sample_meta,
            }
        )
        lock_entries.append(entry)
        print(f"[sync] {dataset['id']}: {len(records)} rows, {sample_count} sampled", flush=True)

    lock = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "manifest_path": str(manifest_path.resolve()),
        "manifest_sha256": sha256_bytes(manifest_bytes),
        "tier": tier,
        "seed": seed,
        "datasets": lock_entries,
    }
    lock_path = output_root / "quality-datasets.lock.json"
    lock_path.write_text(json.dumps(lock, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Lock: {lock_path}")
    return lock


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync pinned open-source XconcepAI quality datasets")
    parser.add_argument("--manifest", type=Path, default=STACK_ROOT / "quality" / "datasets.json")
    parser.add_argument("--output", type=Path, default=STACK_ROOT / "storage" / "quality-datasets")
    parser.add_argument("--tier", choices=tuple(TIER_ORDER), default="smoke")
    parser.add_argument("--seed", type=int)
    parser.add_argument("--offline", action="store_true", help="Do not use the network; verify and resample cached artifacts")
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    seed = args.seed if args.seed is not None else int(manifest["default_seed"])
    sync(args.manifest.resolve(), args.output.resolve(), args.tier, seed, args.offline)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
