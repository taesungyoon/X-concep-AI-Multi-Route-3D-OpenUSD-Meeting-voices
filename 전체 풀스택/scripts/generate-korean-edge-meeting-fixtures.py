"""Create high-clarity Korean meeting MP3 fixtures through edge-tts.

This is an online QA-fixture generator, not a production dependency. Korean
voice identifiers are published by Microsoft; generated files stay in the
git-ignored storage directory. Review Microsoft service terms before sharing.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
from pathlib import Path

import edge_tts


UTTERANCES = [
    {
        "id": "equipment-envelope",
        "voice": "ko-KR-SunHiNeural",
        "text": (
            "설비 설계 회의를 시작합니다. 장비 외곽은 폭 천이백 밀리미터, "
            "깊이 팔백 밀리미터, 높이 천육백 밀리미터로 확정합니다."
        ),
    },
    {
        "id": "equipment-components",
        "voice": "ko-KR-InJoonNeural",
        "text": (
            "중앙에는 컨베이어를 배치하고 상단에는 비전 카메라를 설치합니다. "
            "구동부는 서보 모터를 사용하고 오른쪽에는 제어반을 둡니다."
        ),
    },
    {
        "id": "equipment-safety",
        "voice": "ko-KR-SunHiNeural",
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


async def generate(output_dir: Path) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    records = []
    for index, utterance in enumerate(UTTERANCES, start=1):
        path = output_dir / f"meeting-{index:02d}-{utterance['id']}.mp3"
        communicate = edge_tts.Communicate(
            utterance["text"],
            utterance["voice"],
            rate="-8%",
        )
        await communicate.save(str(path))
        records.append({**utterance, "file": path.name, "sha256": sha256(path)})

    return {
        "schema": "xconcep.audio-fixtures/1.0",
        "purpose": "internal Korean industrial meeting ASR E2E",
        "generator": "edge-tts 7.2.8",
        "voice_reference": (
            "https://learn.microsoft.com/azure/ai-services/"
            "speech-service/language-support"
        ),
        "runtime_source": "https://github.com/rany2/edge-tts",
        "distribution_note": "Internal QA only; review Microsoft service terms before sharing.",
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


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate Korean meeting MP3 fixtures")
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    manifest = asyncio.run(generate(args.output_dir))
    (args.output_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
