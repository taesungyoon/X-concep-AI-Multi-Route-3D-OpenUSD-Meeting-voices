"""Run with Kit Python. Validates a local or omniverse:// OpenUSD asset."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import omni.asset_validator.core


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("asset")
    parser.add_argument("--json", dest="json_path", default="")
    args = parser.parse_args()

    engine = omni.asset_validator.core.ValidationEngine()
    result = engine.validate(args.asset)
    payload = {
        "asset": str(getattr(result, "asset", args.asset)),
        "issues": [str(issue) for issue in (getattr(result, "issues", []) or [])],
    }
    text = json.dumps(payload, ensure_ascii=False, indent=2)

    if args.json_path:
        target = Path(args.json_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
