from __future__ import annotations

import argparse
import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


STACK_ROOT = Path(__file__).resolve().parents[1]
SAFE_IDENTIFIER = re.compile(r"^[A-Za-z0-9_]+$")


def _run(command: list[str], *, input_bytes: bytes | None = None, timeout: int = 300) -> subprocess.CompletedProcess[bytes]:
    completed = subprocess.run(command, input=input_bytes, capture_output=True, timeout=timeout, check=False)
    if completed.returncode != 0:
        stderr = completed.stderr.decode("utf-8", errors="replace")[-3000:]
        raise RuntimeError(f"command failed ({completed.returncode}): {command[:5]}\n{stderr}")
    return completed


def _compose_prefix(compose_file: Path, project: str) -> list[str]:
    return ["docker", "compose", "--project-name", project, "-f", str(compose_file)]


def _mysql(prefix: list[str], sql: str, database: str | None = None) -> str:
    command = prefix + ["exec", "-T", "mysql", "sh", "-lc"]
    db_arg = f" {database}" if database else ""
    shell = f'exec mysql -uroot -p"$MYSQL_ROOT_PASSWORD" -N -B{db_arg} -e {json.dumps(sql)}'
    completed = _run(command + [shell])
    return completed.stdout.decode("utf-8", errors="replace").strip()


def _table_counts(prefix: list[str], database: str) -> dict[str, int]:
    tables_text = _mysql(
        prefix,
        f"SELECT TABLE_NAME FROM information_schema.TABLES WHERE TABLE_SCHEMA='{database}' AND TABLE_TYPE='BASE TABLE' ORDER BY TABLE_NAME",
    )
    tables = [line.strip() for line in tables_text.splitlines() if line.strip()]
    counts = {}
    for table in tables:
        if not SAFE_IDENTIFIER.fullmatch(table):
            raise RuntimeError(f"unsafe table identifier returned by MySQL: {table!r}")
        value = _mysql(prefix, f"SELECT COUNT(*) FROM {table}", database)
        counts[table] = int(value)
    return counts


def verify(compose_file: Path, project: str, source_db: str, verify_db: str, output_root: Path, start: bool) -> dict[str, Any]:
    if not SAFE_IDENTIFIER.fullmatch(source_db) or not SAFE_IDENTIFIER.fullmatch(verify_db):
        raise ValueError("database names may contain only ASCII letters, digits, and underscore")
    if source_db == verify_db:
        raise ValueError("verification database must differ from source database")
    prefix = _compose_prefix(compose_file, project)
    if start:
        _run(prefix + ["up", "-d", "mysql"], timeout=600)
    _run(prefix + ["exec", "-T", "mysql", "sh", "-lc", 'exec mysqladmin ping -h 127.0.0.1 -uroot -p"$MYSQL_ROOT_PASSWORD"'])

    run_id = datetime.now().strftime("%Y%m%d-%H%M%S")
    run_root = output_root / run_id
    run_root.mkdir(parents=True, exist_ok=False)
    backup_path = run_root / f"{source_db}.sql"
    report_path = run_root / "report.json"
    source_counts: dict[str, int] = {}
    restored_counts: dict[str, int] = {}
    try:
        dump_shell = f'exec mysqldump -uroot -p"$MYSQL_ROOT_PASSWORD" --single-transaction --routines --events --hex-blob {source_db}'
        dump = _run(prefix + ["exec", "-T", "mysql", "sh", "-lc", dump_shell], timeout=600).stdout
        if len(dump) < 100:
            raise RuntimeError("mysqldump output is unexpectedly small")
        backup_path.write_bytes(dump)
        source_counts = _table_counts(prefix, source_db)
        _mysql(prefix, f"DROP DATABASE IF EXISTS {verify_db}; CREATE DATABASE {verify_db} CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
        restore_shell = f'exec mysql -uroot -p"$MYSQL_ROOT_PASSWORD" {verify_db}'
        _run(prefix + ["exec", "-T", "mysql", "sh", "-lc", restore_shell], input_bytes=dump, timeout=600)
        restored_counts = _table_counts(prefix, verify_db)
        passed = bool(source_counts) and source_counts == restored_counts
        report = {
            "schema_version": 1,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "source_database": source_db,
            "verification_database": verify_db,
            "backup_path": str(backup_path),
            "backup_size_bytes": len(dump),
            "source_table_counts": source_counts,
            "restored_table_counts": restored_counts,
            "passed": passed,
        }
    finally:
        try:
            _mysql(prefix, f"DROP DATABASE IF EXISTS {verify_db}")
        except Exception:
            pass
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    (output_root / "latest.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Back up internal MySQL, restore into an isolated database, compare exact table counts, then drop it")
    parser.add_argument("--compose-file", type=Path, default=STACK_ROOT / "docker-compose.yml")
    parser.add_argument("--project", default="xconcep")
    parser.add_argument("--source-db", default="xconcep")
    parser.add_argument("--verify-db", default="xconcep_restore_verify")
    parser.add_argument("--output", type=Path, default=STACK_ROOT / "storage" / "backups" / "mysql")
    parser.add_argument("--start", action="store_true")
    args = parser.parse_args()
    report = verify(args.compose_file.resolve(), args.project, args.source_db, args.verify_db, args.output.resolve(), args.start)
    print(json.dumps({"passed": report["passed"], "tables": len(report["source_table_counts"]), "backup_size_bytes": report["backup_size_bytes"]}, ensure_ascii=False))
    print(f"Report: {args.output.resolve() / 'latest.json'}")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
