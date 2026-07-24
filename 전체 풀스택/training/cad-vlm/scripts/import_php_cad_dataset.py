from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PACKAGE_ROOT / "src"))

from xconcep_cad_vlm.dataset import DatasetValidationError
from xconcep_cad_vlm.php_cad import import_php_cad_packages


def main() -> int:
    parser = argparse.ArgumentParser(description="Import CAD AI Dataset Studio PHP packages into raw CAD-VLM JSONL")
    parser.add_argument("--input", required=True, help="PHP package directory or package ZIP")
    parser.add_argument("--output", required=True, help="new raw output directory")
    parser.add_argument("--license", required=True, help="approved training license identifier")
    parser.add_argument("--training-allowed", action="store_true", help="confirm authorization for model training")
    parser.add_argument("--minimum-quality", type=float, default=0.9)
    parser.add_argument("--category-map", default="", help='JSON map, e.g. {"bracket":"part"}')
    args = parser.parse_args()
    try:
        mapping = json.loads(args.category_map) if args.category_map else None
        if mapping is not None and not isinstance(mapping, dict):
            raise ValueError("category map must be a JSON object")
        report = import_php_cad_packages(args.input, args.output, license_id=args.license, training_allowed=args.training_allowed, category_map=mapping, minimum_quality=args.minimum_quality)
    except (DatasetValidationError, OSError, ValueError, json.JSONDecodeError) as exc:
        parser.error(str(exc))
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
