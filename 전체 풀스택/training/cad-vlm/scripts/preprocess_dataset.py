from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PACKAGE_ROOT / "src"))

from xconcep_cad_vlm.dataset import DatasetValidationError
from xconcep_cad_vlm.preprocess import preprocess_dataset


def main() -> int:
    parser = argparse.ArgumentParser(description="Convert raw CAD/VLM JSONL and images into a validated Xconcep dataset")
    parser.add_argument("--input", required=True, help="raw JSONL manifest; image paths are resolved from its directory")
    parser.add_argument("--output", required=True, help="new output directory; it must not already exist")
    parser.add_argument("--max-image-side", type=int, default=2048)
    parser.add_argument("--min-images", type=int, default=1)
    parser.add_argument("--split", default="0.8,0.1,0.1", help="train,eval,test ratios; must sum to 1")
    parser.add_argument("--license-allowlist", default="")
    args = parser.parse_args()
    try:
        ratios = tuple(float(value.strip()) for value in args.split.split(","))
        report = preprocess_dataset(
            args.input,
            args.output,
            max_image_side=args.max_image_side,
            min_images=args.min_images,
            split_ratios=ratios,  # type: ignore[arg-type]
            allowlist_path=args.license_allowlist or None,
        )
    except (DatasetValidationError, OSError, ValueError) as exc:
        parser.error(str(exc))
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
