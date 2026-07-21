from __future__ import annotations

import json
import sys
from pathlib import Path

from pxr import Sdf


REQUIRED_PRIMS = (
    "/World",
    "/OVCamera",
    "/Render/OVServer/ViewportTexture0",
    "/Render/Vars/LdrColor",
    "/Render/OVRenderSettings",
)


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit("usage: pxr_validate.py STAGE.usda")
    stage_path = Path(sys.argv[1]).resolve()
    layer = Sdf.Layer.FindOrOpen(str(stage_path))
    if layer is None:
        raise RuntimeError(f"Unable to parse USDA: {stage_path}")
    missing = [path for path in REQUIRED_PRIMS if not layer.GetPrimAtPath(path)]
    if missing:
        raise RuntimeError(f"Generated USDA is missing prims: {', '.join(missing)}")
    print(json.dumps({"ok": True, "stage": str(stage_path), "required_prims": len(REQUIRED_PRIMS)}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
