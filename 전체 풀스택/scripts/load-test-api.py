from __future__ import annotations

import argparse
import concurrent.futures
import json
import statistics
import time
import urllib.request


def request_once(base_url: str, path: str, token: str) -> tuple[bool, float, int]:
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    request = urllib.request.Request(f"{base_url.rstrip('/')}{path}", headers=headers)
    started = time.monotonic()
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            response.read()
            return 200 <= response.status < 400, time.monotonic() - started, response.status
    except Exception as exc:
        return False, time.monotonic() - started, int(getattr(exc, "code", 0) or 0)


def percentile(values: list[float], ratio: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int((len(ordered) - 1) * ratio))]


def main() -> int:
    parser = argparse.ArgumentParser(description="Bounded health/API concurrency test; it never starts generation jobs.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8080")
    parser.add_argument("--path", default="/api/system-status")
    parser.add_argument("--token", default="")
    parser.add_argument("--concurrency", type=int, default=4)
    parser.add_argument("--requests", type=int, default=40)
    args = parser.parse_args()
    if not (1 <= args.concurrency <= 64 and 1 <= args.requests <= 10000):
        parser.error("concurrency must be 1..64 and requests must be 1..10000")
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.concurrency) as executor:
        results = list(executor.map(lambda _: request_once(args.base_url, args.path, args.token), range(args.requests)))
    durations = [duration for _ok, duration, _status in results]
    passed = sum(1 for ok, _duration, _status in results if ok)
    payload = {
        "result": "pass" if passed == args.requests else "fail",
        "requests": args.requests,
        "passed": passed,
        "failed": args.requests - passed,
        "concurrency": args.concurrency,
        "latency_seconds": {
            "mean": round(statistics.mean(durations), 4),
            "p50": round(percentile(durations, 0.50), 4),
            "p95": round(percentile(durations, 0.95), 4),
            "max": round(max(durations), 4),
        },
        "generation_requests_sent": 0,
    }
    print(json.dumps(payload, indent=2))
    return 0 if passed == args.requests else 1


if __name__ == "__main__":
    raise SystemExit(main())
