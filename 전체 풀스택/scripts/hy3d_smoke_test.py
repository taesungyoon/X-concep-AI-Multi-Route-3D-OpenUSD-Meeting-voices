#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import json
import time
import urllib.request
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description="Smoke-test the local Hunyuan3D /generate adapter")
    parser.add_argument("image", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--url", default="http://127.0.0.1:8081/generate")
    parser.add_argument("--token", default="")
    args = parser.parse_args()

    payload = json.dumps({
        "image": base64.b64encode(args.image.read_bytes()).decode("ascii"),
        "remove_background": True,
        "type": "glb",
    }).encode()
    headers = {"Content-Type": "application/json"}
    if args.token:
        headers["Authorization"] = f"Bearer {args.token}"
    started = time.monotonic()
    with urllib.request.urlopen(urllib.request.Request(args.url, data=payload, headers=headers), timeout=1800) as response:
        model = response.read()
    if model[:4] != b"glTF":
        raise RuntimeError("adapter returned invalid GLB")
    args.output.write_bytes(model)
    print(f"PASS status=200 seconds={time.monotonic() - started:.1f} bytes={len(model)} output={args.output}")


if __name__ == "__main__":
    main()
