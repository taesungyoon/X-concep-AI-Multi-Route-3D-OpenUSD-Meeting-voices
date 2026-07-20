from __future__ import annotations

from pathlib import Path
from typing import Any
import json
import tempfile


def nemo_diarize(audio_path: Path, config_path: str) -> list[dict[str, Any]]:
    """Run NVIDIA NeMo offline clustering diarization using an operator config.

    This path is intentionally opt-in because diarization models and configs are
    deployment-specific.  It never fabricates speakers when diarization is not
    enabled or fails.
    """
    if not config_path:
        raise RuntimeError("NEMO_DIARIZER_CONFIG가 설정되지 않음")
    cfg_path = Path(config_path)
    if not cfg_path.exists():
        raise FileNotFoundError(f"NeMo diarizer config를 찾을 수 없음: {cfg_path}")
    try:
        from omegaconf import OmegaConf  # type: ignore
        from nemo.collections.asr.models import ClusteringDiarizer  # type: ignore
    except ImportError as exc:
        raise RuntimeError("NeMo diarization에는 nemo_toolkit[asr]와 omegaconf가 필요함") from exc

    with tempfile.TemporaryDirectory(prefix="xconcep-diarizer-") as td:
        out_dir = Path(td) / "output"
        manifest = Path(td) / "manifest.json"
        manifest.write_text(
            json.dumps(
                {
                    "audio_filepath": str(audio_path.resolve()),
                    "offset": 0,
                    "duration": None,
                    "label": "infer",
                    "text": "-",
                    "num_speakers": None,
                    "rttm_filepath": None,
                    "uem_filepath": None,
                },
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
        cfg = OmegaConf.load(str(cfg_path))
        cfg.diarizer.manifest_filepath = str(manifest)
        cfg.diarizer.out_dir = str(out_dir)
        diarizer = ClusteringDiarizer(cfg=cfg)
        diarizer.diarize()
        candidates = list(out_dir.rglob("*.rttm"))
        if not candidates:
            raise RuntimeError("NeMo diarizer가 RTTM을 생성하지 않음")
        return parse_rttm(candidates[0])


def parse_rttm(path: Path) -> list[dict[str, Any]]:
    intervals: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        fields = line.split()
        if len(fields) < 8 or fields[0].upper() != "SPEAKER":
            continue
        start = float(fields[3])
        duration = float(fields[4])
        intervals.append({"start": start, "end": start + duration, "speaker": fields[7]})
    return intervals


def apply_speakers(segments: list[dict[str, Any]], intervals: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not intervals:
        return segments
    output: list[dict[str, Any]] = []
    for segment in segments:
        item = dict(segment)
        midpoint = (float(item.get("start", 0)) + float(item.get("end", 0))) / 2
        match = next((x for x in intervals if float(x["start"]) <= midpoint <= float(x["end"])), None)
        if match:
            item["speaker"] = str(match["speaker"])
        output.append(item)
    return output
