from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path
from typing import Any

import httpx

from .settings import Settings


class LocalSpeechClient:
    """Local meeting STT adapter.

    Modes:
    - mock: deterministic demo transcript
    - nemo_asr: local NVIDIA NeMo ASR model inference
    - faster_whisper: local open-source Whisper fallback
    - nvidia_nim: local NVIDIA Speech NIM / Riva-compatible gateway supplied by operator
    """

    def __init__(self, settings: Settings):
        self.settings = settings
        self._model = None
        self._whisper_device = ""

    def transcribe(self, audio_path: Path, language: str = "ko", chunk_index: int = 0) -> dict[str, Any]:
        if not audio_path.exists():
            raise FileNotFoundError(f"음성 파일을 찾을 수 없음: {audio_path}")
        if self.settings.speech_mode == "mock":
            result = self._mock(chunk_index)
        elif self.settings.speech_mode == "nemo_asr":
            result = self._nemo_asr(audio_path, language)
        elif self.settings.speech_mode == "faster_whisper":
            result = self._faster_whisper(audio_path, language)
        elif self.settings.speech_mode == "nvidia_nim":
            result = self._nvidia_nim(audio_path, language)
        else:
            raise RuntimeError(f"지원하지 않는 SPEECH_MODE: {self.settings.speech_mode}")
        if self.settings.diarization_mode == "nemo" and self.settings.speech_mode != "mock":
            from .diarization import nemo_diarize, apply_speakers
            intervals = nemo_diarize(audio_path, self.settings.nemo_diarizer_config)
            result["segments"] = apply_speakers(result.get("segments", []), intervals)
            result["diarization_provider"] = "NVIDIA NeMo ClusteringDiarizer"
        else:
            result["diarization_provider"] = "none"
        return result


    def _nemo_asr(self, audio_path: Path, language: str) -> dict[str, Any]:
        try:
            import nemo.collections.asr as nemo_asr  # type: ignore
        except ImportError as exc:
            raise RuntimeError("NVIDIA NeMo ASR가 설치되지 않음. requirements-nemo-speech.txt를 설치해야 함") from exc
        if self._model is None:
            self._model = nemo_asr.models.ASRModel.from_pretrained(model_name=self.settings.nemo_asr_model)
        upload_path = audio_path
        temp_dir: tempfile.TemporaryDirectory[str] | None = None
        try:
            if audio_path.suffix.lower() != ".wav":
                temp_dir = tempfile.TemporaryDirectory(prefix="xconcep-nemo-asr-")
                upload_path = Path(temp_dir.name) / "chunk.wav"
                subprocess.run(["ffmpeg","-y","-i",str(audio_path),"-ac","1","-ar","16000",str(upload_path)],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            output = self._model.transcribe([str(upload_path)])
            first = output[0] if output else ""
            text = getattr(first, "text", first) if first is not None else ""
            text = str(text).strip()
        finally:
            if temp_dir is not None: temp_dir.cleanup()
        segments = [{"start":0.0,"end":0.0,"speaker":"SPEAKER_00","text":text,"confidence":0.9}] if text else []
        return {"text":text,"segments":segments,"language":language,"duration":0.0,"provider":"NVIDIA NeMo ASR local"}

    def _faster_whisper(self, audio_path: Path, language: str) -> dict[str, Any]:
        try:
            from faster_whisper import WhisperModel  # type: ignore
        except ImportError as exc:
            raise RuntimeError("faster-whisper가 설치되지 않음. requirements-speech.txt를 설치해야 함") from exc
        requested_device = self.settings.whisper_device.strip().lower()
        device = self._resolve_whisper_device(requested_device)
        try:
            result_segments, text_parts, info = self._run_whisper(
                WhisperModel, audio_path, language, device
            )
        except Exception:
            if requested_device != "auto" or device == "cpu":
                raise
            self._model = None
            result_segments, text_parts, info = self._run_whisper(
                WhisperModel, audio_path, language, "cpu"
            )
        return {
            "text": " ".join(text_parts),
            "segments": result_segments,
            "language": getattr(info, "language", language),
            "duration": float(getattr(info, "duration", result_segments[-1]["end"] if result_segments else 0.0)),
            "provider": "faster-whisper local",
        }

    @staticmethod
    def _resolve_whisper_device(requested_device: str) -> str:
        if requested_device != "auto":
            return requested_device
        try:
            import ctranslate2  # type: ignore
            return "cuda" if ctranslate2.get_cuda_device_count() > 0 else "cpu"
        except Exception:
            return "cpu"

    def _run_whisper(self, model_class: Any, audio_path: Path, language: str, device: str):
        if self._model is None or self._whisper_device != device:
            self.settings.whisper_model_cache.mkdir(parents=True, exist_ok=True)
            compute_type = self.settings.whisper_compute_type
            if compute_type.strip().lower() == "auto":
                compute_type = "float16" if device == "cuda" else "int8"
            self._model = model_class(
                self.settings.whisper_model,
                device=device,
                compute_type=compute_type,
                download_root=str(self.settings.whisper_model_cache),
            )
            self._whisper_device = device
        segments, info = self._model.transcribe(
            str(audio_path),
            language=language or None,
            vad_filter=True,
            beam_size=5,
            condition_on_previous_text=False,
        )
        result_segments = []
        text_parts = []
        for segment in segments:
            text = segment.text.strip()
            if not text:
                continue
            result_segments.append({
                "start": float(segment.start),
                "end": float(segment.end),
                "speaker": "SPEAKER_00",
                "text": text,
                "confidence": max(0.0, min(1.0, 1.0 - float(getattr(segment, "no_speech_prob", 0.2)))),
            })
            text_parts.append(text)
        return result_segments, text_parts, info

    def _nvidia_nim(self, audio_path: Path, language: str) -> dict[str, Any]:
        headers = {}
        if self.settings.nvidia_asr_api_key:
            headers["Authorization"] = f"Bearer {self.settings.nvidia_asr_api_key}"

        language_code = {"ko": "multi", "ko-KR": "multi"}.get(language, language or "multi")
        endpoint = f"{self.settings.nvidia_asr_url}{self.settings.nvidia_asr_transcribe_path}"
        upload_path = audio_path
        temp_dir: tempfile.TemporaryDirectory[str] | None = None
        try:
            if audio_path.suffix.lower() not in {".wav", ".flac", ".opus"}:
                temp_dir = tempfile.TemporaryDirectory(prefix="xconcep-asr-")
                converted = Path(temp_dir.name) / "chunk.wav"
                subprocess.run(
                    ["ffmpeg", "-y", "-i", str(audio_path), "-ac", "1", "-ar", "16000", str(converted)],
                    check=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                upload_path = converted
            with upload_path.open("rb") as stream:
                files = {"file": (upload_path.name, stream, "audio/wav" if upload_path.suffix == ".wav" else "application/octet-stream")}
                data = {"language": language_code, "response_format": "json"}
                with httpx.Client(timeout=300) as client:
                    response = client.post(endpoint, headers=headers, files=files, data=data)
                    response.raise_for_status()
            payload = response.json()
        finally:
            if temp_dir is not None:
                temp_dir.cleanup()

        text = str(payload.get("text") or "").strip()
        raw_segments = payload.get("segments") or []
        segments = []
        for index, segment in enumerate(raw_segments):
            if not isinstance(segment, dict):
                continue
            segment_text = str(segment.get("text") or "").strip()
            if not segment_text:
                continue
            segments.append({
                "start": float(segment.get("start", 0)),
                "end": float(segment.get("end", segment.get("start", 0))),
                "speaker": str(segment.get("speaker") or segment.get("speaker_label") or "SPEAKER_00"),
                "text": segment_text,
                "confidence": float(segment.get("confidence", 0.9)),
            })
        if not segments and text:
            segments = [{"start": 0, "end": 0, "speaker": "SPEAKER_00", "text": text, "confidence": 0.9}]
        return {
            "text": text,
            "segments": segments,
            "language": language_code,
            "duration": 0,
            "provider": "NVIDIA Speech NIM HTTP REST local",
        }

    @staticmethod
    def _mock(chunk_index: int) -> dict[str, Any]:
        examples = [
            ("고객", "FPCB 끝단을 90도로 접는 단일 유닛으로 구성해주세요."),
            ("설계", "서보모터 구동과 전면 투입 구조로 검토하겠습니다."),
            ("고객", "투명 안전커버와 우측 제어반도 포함해주세요."),
            ("설계", "전체 폭은 800밀리미터 이내로 우선 반영하겠습니다."),
        ]
        speaker_name, text = examples[chunk_index % len(examples)]
        return {
            "text": text,
            "segments": [{
                "start": float(chunk_index * 15),
                "end": float(chunk_index * 15 + 8),
                "speaker": speaker_name,
                "text": text,
                "confidence": 0.96,
            }],
            "language": "ko",
            "duration": 8.0,
            "provider": "mock",
        }
