from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PACKAGE_ROOT / "src"))

from xconcep_cad_vlm.dataset import DatasetValidationError, validate_dataset


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate Xconcep CAD VLM dataset before GPU training")
    parser.add_argument("--dataset", default=str(PACKAGE_ROOT / "data" / "examples"))
    parser.add_argument("--skip-image-decode", action="store_true")
    parser.add_argument("--report")
    args = parser.parse_args()
    try:
        report = validate_dataset(args.dataset, open_images=not args.skip_image_decode)
    except DatasetValidationError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    output = json.dumps(report, ensure_ascii=False, indent=2)
    print(output)
    if args.report:
        Path(args.report).write_text(output + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

