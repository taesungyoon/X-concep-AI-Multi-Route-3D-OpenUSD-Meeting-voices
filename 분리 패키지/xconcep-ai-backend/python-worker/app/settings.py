from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    storage_path: Path
    pipeline_mode: str
    llm_mode: str
    vllm_base_url: str
    vllm_api_key: str
    gemma_model_name: str
    llm_timeout_seconds: int
    openai_image_mode: str
    openai_api_key: str
    openai_image_model: str
    openai_image_size: str
    openai_image_quality: str
    hunyuan_mode: str
    hunyuan_api_url: str
    hunyuan_timeout_seconds: int
    hunyuan_texture: bool
    openscad_mode: str
    openscad_bin: str
    openscad_timeout_seconds: int
    blender_mode: str
    blender_bin: str
    blender_timeout_seconds: int
    openusd_generate_usdc: bool
    public_storage_prefix: str
    speech_mode: str
    whisper_model: str
    whisper_device: str
    whisper_compute_type: str
    nvidia_asr_url: str
    nvidia_asr_api_key: str
    nemo_asr_model: str
    nemo_diarizer_config: str
    nvidia_asr_transcribe_path: str
    diarization_mode: str
    pyannote_token: str
    meeting_chunk_seconds: int
    omniverse_enabled: bool
    omniverse_nucleus_url: str
    omniverse_stream_url: str
    omniverse_generate_layers: bool
    omniverse_enable_physics: bool
    omniverse_enable_variants: bool
    routing_low_confidence: float
    routing_high_confidence: float
    validation_dimension_tolerance_pct: float
    enable_parallel_preview: bool


def _bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def get_settings() -> Settings:
    root = Path(__file__).resolve().parents[2]
    return Settings(
        storage_path=Path(os.getenv("STORAGE_PATH", root / "storage")),
        pipeline_mode=os.getenv("PIPELINE_MODE", "mock").strip().lower(),
        llm_mode=os.getenv("LLM_MODE", "mock").strip().lower(),
        vllm_base_url=os.getenv("VLLM_BASE_URL", "http://127.0.0.1:8000/v1").rstrip("/"),
        vllm_api_key=os.getenv("VLLM_API_KEY", "local-not-required"),
        gemma_model_name=os.getenv("GEMMA_MODEL_NAME", "gemma-4-64b-local"),
        llm_timeout_seconds=int(os.getenv("LLM_TIMEOUT_SECONDS", "180")),
        openai_image_mode=os.getenv("OPENAI_IMAGE_MODE", "mock").strip().lower(),
        openai_api_key=os.getenv("OPENAI_API_KEY", ""),
        openai_image_model=os.getenv("OPENAI_IMAGE_MODEL", "gpt-image-2"),
        openai_image_size=os.getenv("OPENAI_IMAGE_SIZE", "1536x1024"),
        openai_image_quality=os.getenv("OPENAI_IMAGE_QUALITY", "medium"),
        hunyuan_mode=os.getenv("HUNYUAN_MODE", "mock").strip().lower(),
        hunyuan_api_url=os.getenv("HUNYUAN_API_URL", "http://127.0.0.1:8081").rstrip("/"),
        hunyuan_timeout_seconds=int(os.getenv("HUNYUAN_TIMEOUT_SECONDS", "1800")),
        hunyuan_texture=_bool("HUNYUAN_TEXTURE", True),
        openscad_mode=os.getenv("OPENSCAD_MODE", "auto").strip().lower(),
        openscad_bin=os.getenv("OPENSCAD_BIN", "openscad"),
        openscad_timeout_seconds=int(os.getenv("OPENSCAD_TIMEOUT_SECONDS", "600")),
        blender_mode=os.getenv("BLENDER_MODE", "auto").strip().lower(),
        blender_bin=os.getenv("BLENDER_BIN", "blender"),
        blender_timeout_seconds=int(os.getenv("BLENDER_TIMEOUT_SECONDS", "1800")),
        openusd_generate_usdc=_bool("OPENUSD_GENERATE_USDC", True),
        public_storage_prefix=os.getenv("PUBLIC_STORAGE_PREFIX", "/storage").rstrip("/"),
        speech_mode=os.getenv("SPEECH_MODE", "mock").strip().lower(),
        whisper_model=os.getenv("WHISPER_MODEL", "large-v3-turbo"),
        whisper_device=os.getenv("WHISPER_DEVICE", "cuda"),
        whisper_compute_type=os.getenv("WHISPER_COMPUTE_TYPE", "float16"),
        nvidia_asr_url=os.getenv("NVIDIA_ASR_URL", "http://127.0.0.1:9000").rstrip("/"),
        nvidia_asr_api_key=os.getenv("NVIDIA_ASR_API_KEY", ""),
        nemo_asr_model=os.getenv("NEMO_ASR_MODEL", "nvidia/parakeet-tdt-0.6b-v3"),
        nemo_diarizer_config=os.getenv("NEMO_DIARIZER_CONFIG", ""),
        nvidia_asr_transcribe_path=os.getenv("NVIDIA_ASR_TRANSCRIBE_PATH", "/v1/audio/transcriptions"),
        diarization_mode=os.getenv("DIARIZATION_MODE", "none").strip().lower(),
        pyannote_token=os.getenv("PYANNOTE_TOKEN", ""),
        meeting_chunk_seconds=int(os.getenv("MEETING_CHUNK_SECONDS", "15")),
        omniverse_enabled=_bool("OMNIVERSE_ENABLED", True),
        omniverse_nucleus_url=os.getenv("OMNIVERSE_NUCLEUS_URL", "").rstrip("/"),
        omniverse_stream_url=os.getenv("OMNIVERSE_STREAM_URL", "").rstrip("/"),
        omniverse_generate_layers=_bool("OMNIVERSE_GENERATE_LAYERS", True),
        omniverse_enable_physics=_bool("OMNIVERSE_ENABLE_PHYSICS", True),
        omniverse_enable_variants=_bool("OMNIVERSE_ENABLE_VARIANTS", True),
        routing_low_confidence=float(os.getenv("ROUTING_LOW_CONFIDENCE", "0.60")),
        routing_high_confidence=float(os.getenv("ROUTING_HIGH_CONFIDENCE", "0.80")),
        validation_dimension_tolerance_pct=float(os.getenv("VALIDATION_DIMENSION_TOLERANCE_PCT", "5.0")),
        enable_parallel_preview=_bool("ENABLE_PARALLEL_PREVIEW", True),
    )
