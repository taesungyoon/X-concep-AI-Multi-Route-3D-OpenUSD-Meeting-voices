from __future__ import annotations

import argparse
import json
import platform
import shutil
import subprocess
import sys


def main() -> int:
    parser = argparse.ArgumentParser(description="Check a target GPU server before Xconcep VLM training")
    parser.add_argument("--allow-cpu", action="store_true")
    args = parser.parse_args()
    report = {
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "disk_free_gb": round(shutil.disk_usage(".").free / 1024**3, 1),
        "nvidia_smi": None,
        "torch": None,
        "recommendations": [],
    }
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total,driver_version", "--format=csv,noheader"],
            check=True, capture_output=True, text=True, timeout=15,
        )
        report["nvidia_smi"] = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    except (FileNotFoundError, subprocess.SubprocessError) as exc:
        report["nvidia_smi"] = {"error": str(exc)}
    try:
        import torch
        capability = [list(torch.cuda.get_device_capability(index)) for index in range(torch.cuda.device_count())] if torch.cuda.is_available() else []
        architectures = list(torch.cuda.get_arch_list()) if torch.cuda.is_available() else []
        unsupported = [f"sm_{major}{minor}" for major, minor in capability if f"sm_{major}{minor}" not in architectures]
        report["torch"] = {
            "version": torch.__version__,
            "cuda_available": torch.cuda.is_available(),
            "cuda_version": torch.version.cuda,
            "bf16_supported": bool(torch.cuda.is_available() and torch.cuda.is_bf16_supported()),
            "device_count": torch.cuda.device_count(),
            "device_capability": capability,
            "compiled_architectures": architectures,
            "unsupported_architectures": unsupported,
        }
    except ImportError:
        report["torch"] = {"error": "torch is not installed"}
    if report["disk_free_gb"] < 100:
        report["recommendations"].append("Keep at least 100 GB free for model, cache, data and checkpoints.")
    cuda_ok = isinstance(report["torch"], dict) and report["torch"].get("cuda_available") is True
    if not cuda_ok:
        report["recommendations"].append("Install a CUDA-compatible PyTorch build before training.")
    if isinstance(report["torch"], dict) and report["torch"].get("unsupported_architectures"):
        report["recommendations"].append("Use a PyTorch image compiled for the listed GPU architecture before training.")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    unsupported = isinstance(report["torch"], dict) and bool(report["torch"].get("unsupported_architectures"))
    return 0 if (cuda_ok and not unsupported) or args.allow_cpu else 2


if __name__ == "__main__":
    raise SystemExit(main())
