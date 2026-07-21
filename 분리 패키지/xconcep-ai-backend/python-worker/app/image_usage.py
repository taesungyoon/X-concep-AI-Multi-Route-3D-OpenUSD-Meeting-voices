from __future__ import annotations

import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


class ImageBudgetExceeded(RuntimeError):
    pass


@dataclass(frozen=True)
class UsageReservation:
    request_id: str
    estimated_cost_usd: float


class OpenAIImageUsageLedger:
    """Local, secret-free audit and budget ledger for billable image calls."""

    def __init__(
        self,
        path: Path,
        *,
        max_requests_per_day: int,
        estimated_cost_usd: float,
        max_estimated_cost_usd_per_day: float,
    ) -> None:
        self.path = path
        self.max_requests_per_day = max(0, max_requests_per_day)
        self.estimated_cost_usd = max(0.0, estimated_cost_usd)
        self.max_estimated_cost_usd_per_day = max(0.0, max_estimated_cost_usd_per_day)

    def _connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path, timeout=30.0)
        connection.execute("PRAGMA busy_timeout=30000")
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS image_api_usage (
                request_id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                project_id TEXT NOT NULL,
                variant_index INTEGER NOT NULL,
                model TEXT NOT NULL,
                size TEXT NOT NULL,
                quality TEXT NOT NULL,
                prompt_sha256 TEXT NOT NULL,
                estimated_cost_usd REAL NOT NULL,
                status TEXT NOT NULL,
                http_status INTEGER,
                duration_seconds REAL,
                provider_request_id TEXT,
                error_type TEXT
            )
            """
        )
        return connection

    def reserve(
        self,
        *,
        project_id: str,
        variant_index: int,
        model: str,
        size: str,
        quality: str,
        prompt_sha256: str,
    ) -> UsageReservation:
        now = datetime.now(timezone.utc)
        day_prefix = now.date().isoformat() + "%"
        request_id = str(uuid.uuid4())
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            count, spent = connection.execute(
                "SELECT COUNT(*), COALESCE(SUM(estimated_cost_usd), 0) "
                "FROM image_api_usage WHERE created_at LIKE ?",
                (day_prefix,),
            ).fetchone()
            if self.max_requests_per_day and int(count) >= self.max_requests_per_day:
                raise ImageBudgetExceeded(
                    f"OpenAI Image daily request ceiling reached: {count}/{self.max_requests_per_day}"
                )
            projected = float(spent) + self.estimated_cost_usd
            if (
                self.max_estimated_cost_usd_per_day
                and projected > self.max_estimated_cost_usd_per_day
            ):
                raise ImageBudgetExceeded(
                    "OpenAI Image estimated daily budget would be exceeded: "
                    f"{projected:.4f} > {self.max_estimated_cost_usd_per_day:.4f} USD"
                )
            connection.execute(
                "INSERT INTO image_api_usage VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, NULL, NULL)",
                (
                    request_id,
                    now.isoformat(),
                    project_id,
                    variant_index,
                    model,
                    size,
                    quality,
                    prompt_sha256,
                    self.estimated_cost_usd,
                    "reserved",
                ),
            )
        return UsageReservation(request_id=request_id, estimated_cost_usd=self.estimated_cost_usd)

    def finish(
        self,
        request_id: str,
        *,
        status: str,
        http_status: int | None,
        duration_seconds: float,
        provider_request_id: str = "",
        error_type: str = "",
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                "UPDATE image_api_usage SET status=?, http_status=?, duration_seconds=?, "
                "provider_request_id=?, error_type=? WHERE request_id=?",
                (status, http_status, duration_seconds, provider_request_id, error_type, request_id),
            )

    def today(self) -> dict[str, float | int]:
        day_prefix = datetime.now(timezone.utc).date().isoformat() + "%"
        with self._connect() as connection:
            count, success, spent = connection.execute(
                "SELECT COUNT(*), SUM(CASE WHEN status='success' THEN 1 ELSE 0 END), "
                "COALESCE(SUM(estimated_cost_usd), 0) FROM image_api_usage WHERE created_at LIKE ?",
                (day_prefix,),
            ).fetchone()
        return {
            "requests": int(count),
            "successes": int(success or 0),
            "estimated_cost_usd": round(float(spent), 6),
        }
