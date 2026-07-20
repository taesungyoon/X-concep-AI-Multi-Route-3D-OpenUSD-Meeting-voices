"""Run with Kit Python to publish a layered OpenUSD package to Nucleus."""
from __future__ import annotations

import argparse
from pathlib import Path

import omni.client


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("local_folder")
    parser.add_argument("nucleus_folder", help="omniverse://server/Projects/Xconcep/ProjectId")
    args = parser.parse_args()
    root = Path(args.local_folder).resolve()
    if not root.is_dir():
        raise SystemExit("local_folder is not a directory")
    omni.client.initialize()
    try:
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            relative = path.relative_to(root).as_posix()
            destination = args.nucleus_folder.rstrip("/") + "/" + relative
            result = omni.client.copy_file(str(path), destination, omni.client.CopyBehavior.OVERWRITE)
            if result != omni.client.Result.OK:
                raise RuntimeError(f"copy failed: {path} -> {destination}: {result}")
            print(destination)
    finally:
        omni.client.shutdown()


if __name__ == "__main__":
    main()
