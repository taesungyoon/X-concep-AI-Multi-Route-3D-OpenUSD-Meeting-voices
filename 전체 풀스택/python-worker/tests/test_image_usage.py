from __future__ import annotations

import sqlite3

import pytest

from app.image_usage import ImageBudgetExceeded, OpenAIImageUsageLedger


def _reserve(ledger: OpenAIImageUsageLedger, index: int = 1):
    return ledger.reserve(
        project_id="PRJ-BUDGET",
        variant_index=index,
        model="gpt-image-2",
        size="1536x1024",
        quality="medium",
        prompt_sha256="a" * 64,
    )


def test_usage_ledger_enforces_daily_request_ceiling(tmp_path):
    ledger = OpenAIImageUsageLedger(
        tmp_path / "usage.sqlite3",
        max_requests_per_day=1,
        estimated_cost_usd=0.1,
        max_estimated_cost_usd_per_day=1.0,
    )
    reservation = _reserve(ledger)
    ledger.finish(reservation.request_id, status="success", http_status=200, duration_seconds=1.25)

    with pytest.raises(ImageBudgetExceeded, match="request ceiling"):
        _reserve(ledger, 2)

    assert ledger.today() == {"requests": 1, "successes": 1, "estimated_cost_usd": 0.1}


def test_usage_ledger_does_not_store_prompt_or_secret(tmp_path):
    path = tmp_path / "usage.sqlite3"
    ledger = OpenAIImageUsageLedger(
        path,
        max_requests_per_day=0,
        estimated_cost_usd=0,
        max_estimated_cost_usd_per_day=0,
    )
    _reserve(ledger)

    with sqlite3.connect(path) as connection:
        columns = [row[1] for row in connection.execute("PRAGMA table_info(image_api_usage)")]

    assert "prompt" not in columns
    assert "api_key" not in columns
    assert "prompt_sha256" in columns
