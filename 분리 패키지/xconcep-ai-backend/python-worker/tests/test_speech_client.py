from __future__ import annotations

import sys
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

from app.settings import get_settings
from app.speech_client import LocalSpeechClient


def test_faster_whisper_uses_project_cache_and_maps_segments(tmp_path, monkeypatch):
    audio_path = tmp_path / "sample.wav"
    audio_path.write_bytes(b"RIFF-test")
    created = {}

    class FakeModel:
        def __init__(self, model_name, **kwargs):
            created.update(model_name=model_name, **kwargs)

        def transcribe(self, path, **kwargs):
            assert path == str(audio_path)
            assert kwargs["language"] == "ko"
            return iter([
                SimpleNamespace(start=0.0, end=1.5, text=" 테스트 음성 ", no_speech_prob=0.1)
            ]), SimpleNamespace(language="ko", duration=1.5)

    monkeypatch.setitem(sys.modules, "faster_whisper", SimpleNamespace(WhisperModel=FakeModel))
    settings = replace(
        get_settings(),
        speech_mode="faster_whisper",
        whisper_model="test-model",
        whisper_model_cache=tmp_path / "models",
        whisper_device="cpu",
        whisper_compute_type="auto",
    )

    result = LocalSpeechClient(settings).transcribe(audio_path)

    assert created == {
        "model_name": "test-model",
        "device": "cpu",
        "compute_type": "int8",
        "download_root": str(tmp_path / "models"),
    }
    assert result["text"] == "테스트 음성"
    assert result["segments"][0]["speaker"] == "SPEAKER_00"
    assert result["provider"] == "faster-whisper local"


def test_whisper_auto_device_falls_back_to_cpu(tmp_path, monkeypatch):
    audio_path = tmp_path / "sample.wav"
    audio_path.write_bytes(b"RIFF-test")
    devices = []

    class FakeModel:
        def __init__(self, _model_name, **kwargs):
            self.device = kwargs["device"]
            devices.append(self.device)

        def transcribe(self, _path, **_kwargs):
            if self.device == "cuda":
                raise RuntimeError("CUDA runtime unavailable")
            return iter([]), SimpleNamespace(language="ko", duration=0.0)

    monkeypatch.setitem(sys.modules, "faster_whisper", SimpleNamespace(WhisperModel=FakeModel))
    monkeypatch.setitem(sys.modules, "ctranslate2", SimpleNamespace(get_cuda_device_count=lambda: 1))
    settings = replace(
        get_settings(),
        speech_mode="faster_whisper",
        whisper_model_cache=tmp_path / "models",
        whisper_device="auto",
        whisper_compute_type="auto",
    )

    result = LocalSpeechClient(settings).transcribe(audio_path)

    assert devices == ["cuda", "cpu"]
    assert result["text"] == ""
