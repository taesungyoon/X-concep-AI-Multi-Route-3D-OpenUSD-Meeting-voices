"""Generate Korean industrial-meeting WAV fixtures with an offline Piper model.

The model is downloaded separately from ``neurlang/piper-onnx-kss-korean``.
Its CC BY-NC-SA 4.0 license makes these fixtures suitable for internal,
non-commercial QA; review licensing before redistributing generated audio.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import soundfile as sf
from piper_onnx import Piper


UTTERANCES = [
    {
        "id": "equipment-envelope",
        "text": (
            "설비 설계 회의를 시작합니다. 장비 외곽은 폭 천이백 밀리미터, "
            "깊이 팔백 밀리미터, 높이 천육백 밀리미터로 확정합니다."
        ),
    },
    {
        "id": "equipment-components",
        "text": (
            "중앙에는 컨베이어를 배치하고 상단에는 비전 카메라를 설치합니다. "
            "구동부는 서보 모터를 사용하고 오른쪽에는 제어반을 둡니다."
        ),
    },
    {
        "id": "equipment-safety",
        "text": (
            "전면에는 투명 안전 도어와 비상 정지 버튼 두 개를 적용합니다. "
            "후면 정비 공간은 칠백 밀리미터 이상 확보합니다."
        ),
    },
]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate Korean meeting audio fixtures")
    parser.add_argument("--model-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    model_path = args.model_dir / "piper-kss-korean.onnx"
    config_path = args.model_dir / "piper-kss-korean.onnx.json"
    if not model_path.is_file() or not config_path.is_file():
        raise FileNotFoundError(f"Piper model/config missing below {args.model_dir}")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    # piper-onnx 1.0.6 opens JSON with the Windows ANSI code page. Re-encoding
    # non-ASCII keys as JSON escapes keeps the same data and works on CP949 too.
    portable_config = args.output_dir / ".piper-config-ascii.json"
    portable_config.write_text(
        json.dumps(json.loads(config_path.read_text(encoding="utf-8")), ensure_ascii=True),
        encoding="ascii",
    )
    try:
        piper = Piper(str(model_path), str(portable_config))
    finally:
        portable_config.unlink(missing_ok=True)
    records = []
    for index, utterance in enumerate(UTTERANCES, start=1):
        samples, sample_rate = piper.create(utterance["text"])
        output_path = args.output_dir / f"meeting-{index:02d}-{utterance['id']}.wav"
        sf.write(output_path, samples, sample_rate, subtype="PCM_16")
        records.append(
            {
                **utterance,
                "file": output_path.name,
                "sample_rate": sample_rate,
                "sha256": sha256(output_path),
            }
        )

    manifest = {
        "schema": "xconcep.audio-fixtures/1.0",
        "purpose": "internal Korean industrial meeting ASR E2E",
        "model": "neurlang/piper-onnx-kss-korean",
        "source": "https://huggingface.co/neurlang/piper-onnx-kss-korean",
        "license": "CC-BY-NC-SA-4.0",
        "commercial_redistribution_approved": False,
        "expected_keywords": [
            "설비",
            "폭",
            "깊이",
            "높이",
            "컨베이어",
            "비전",
            "카메라",
            "서보",
            "제어반",
            "안전",
            "비상",
            "정비",
        ],
        "fixtures": records,
    }
    manifest_path = args.output_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
