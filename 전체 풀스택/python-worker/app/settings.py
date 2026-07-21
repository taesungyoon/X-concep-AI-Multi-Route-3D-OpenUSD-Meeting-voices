from __future__ import annotations

import os
import shutil
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
    openai_base_url: str
    openai_organization: str
    openai_project: str
    openai_image_model: str
    openai_image_size: str
    openai_image_quality: str
    openai_image_output_format: str
    openai_image_timeout_seconds: int
    openai_image_max_requests_per_day: int
    openai_image_estimated_cost_usd: float
    openai_image_max_estimated_cost_usd_per_day: float
    openai_image_usage_db: Path
    comfyui_base_url: str
    comfyui_api_key: str
    comfyui_timeout_seconds: int
    comfyui_unet_model: str
    comfyui_clip_model: str
    comfyui_vae_model: str
    comfyui_width: int
    comfyui_height: int
    comfyui_steps: int
    comfyui_cfg: float
    comfyui_max_attempts: int
    image_concept_count: int
    image_min_width: int
    image_min_height: int
    image_min_file_bytes: int
    image_min_channel_stddev: float
    image_require_expected_aspect: bool
    hunyuan_mode: str
    shape_provider: str
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
    whisper_model_cache: Path
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


def _native_binary(env_name: str, command: str, portable_pattern: str, installed_relative: str) -> str:
    explicit = os.getenv(env_name, "").strip()
    if explicit:
        return explicit
    discovered = shutil.which(command)
    if discovered:
        return discovered
    source = Path(__file__).resolve()
    for parent in source.parents:
        matches = sorted((parent / ".native-tools").glob(portable_pattern), reverse=True)
        if matches:
            return str(matches[0])
    program_files = Path(os.getenv("ProgramFiles", r"C:\Program Files")) / installed_relative
    if program_files.is_file():
        return str(program_files)
    return command


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
        openai_image_mode=os.getenv("OPENAI_IMAGE_MODE", "comfyui").strip().lower(),
        openai_api_key=os.getenv("OPENAI_API_KEY", ""),
        openai_base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/"),
        openai_organization=os.getenv("OPENAI_ORGANIZATION", "").strip(),
        openai_project=os.getenv("OPENAI_PROJECT", "").strip(),
        openai_image_model=os.getenv("OPENAI_IMAGE_MODEL", "gpt-image-2"),
        openai_image_size=os.getenv("OPENAI_IMAGE_SIZE", "1536x1024"),
        openai_image_quality=os.getenv("OPENAI_IMAGE_QUALITY", "medium"),
        openai_image_output_format=os.getenv("OPENAI_IMAGE_OUTPUT_FORMAT", "png").strip().lower(),
        openai_image_timeout_seconds=int(os.getenv("OPENAI_IMAGE_TIMEOUT_SECONDS", "600")),
        openai_image_max_requests_per_day=int(os.getenv("OPENAI_IMAGE_MAX_REQUESTS_PER_DAY", "20")),
        openai_image_estimated_cost_usd=float(os.getenv("OPENAI_IMAGE_ESTIMATED_COST_USD", "0")),
        openai_image_max_estimated_cost_usd_per_day=float(os.getenv("OPENAI_IMAGE_MAX_ESTIMATED_COST_USD_PER_DAY", "0")),
        openai_image_usage_db=Path(os.getenv("OPENAI_IMAGE_USAGE_DB", root / "storage" / "usage" / "openai-image.sqlite3")),
        comfyui_base_url=os.getenv("COMFYUI_BASE_URL", "http://127.0.0.1:8188").rstrip("/"),
        comfyui_api_key=os.getenv("COMFYUI_API_KEY", "").strip(),
        comfyui_timeout_seconds=int(os.getenv("COMFYUI_TIMEOUT_SECONDS", "900")),
        comfyui_unet_model=os.getenv("COMFYUI_UNET_MODEL", "flux-2-klein-base-4b-fp8.safetensors"),
        comfyui_clip_model=os.getenv("COMFYUI_CLIP_MODEL", "qwen_3_4b.safetensors"),
        comfyui_vae_model=os.getenv("COMFYUI_VAE_MODEL", "flux2-vae.safetensors"),
        comfyui_width=int(os.getenv("COMFYUI_WIDTH", "1024")),
        comfyui_height=int(os.getenv("COMFYUI_HEIGHT", "1024")),
        comfyui_steps=int(os.getenv("COMFYUI_STEPS", "20")),
        comfyui_cfg=float(os.getenv("COMFYUI_CFG", "5.0")),
        comfyui_max_attempts=max(1, int(os.getenv("COMFYUI_MAX_ATTEMPTS", "2"))),
        image_concept_count=max(1, min(8, int(os.getenv("IMAGE_CONCEPT_COUNT", "4")))),
        image_min_width=max(1, int(os.getenv("IMAGE_MIN_WIDTH", "768"))),
        image_min_height=max(1, int(os.getenv("IMAGE_MIN_HEIGHT", "768"))),
        image_min_file_bytes=max(1, int(os.getenv("IMAGE_MIN_FILE_BYTES", "10000"))),
        image_min_channel_stddev=max(0.0, float(os.getenv("IMAGE_MIN_CHANNEL_STDDEV", "3.0"))),
        image_require_expected_aspect=_bool("IMAGE_REQUIRE_EXPECTED_ASPECT", True),
        hunyuan_mode=os.getenv("SHAPE_MODE", os.getenv("HUNYUAN_MODE", "triposr")).strip().lower(),
        shape_provider=os.getenv("SHAPE_PROVIDER", "triposr").strip().lower(),
        hunyuan_api_url=os.getenv("SHAPE_API_URL", os.getenv("HUNYUAN_API_URL", "http://127.0.0.1:8081")).rstrip("/"),
        hunyuan_timeout_seconds=int(os.getenv("SHAPE_TIMEOUT_SECONDS", os.getenv("HUNYUAN_TIMEOUT_SECONDS", "1800"))),
        hunyuan_texture=_bool("SHAPE_TEXTURE", _bool("HUNYUAN_TEXTURE", True)),
        openscad_mode=os.getenv("OPENSCAD_MODE", "auto").strip().lower(),
        openscad_bin=_native_binary("OPENSCAD_BIN", "openscad", "openscad-*/openscad.com", "OpenSCAD/openscad.com"),
        openscad_timeout_seconds=int(os.getenv("OPENSCAD_TIMEOUT_SECONDS", "600")),
        blender_mode=os.getenv("BLENDER_MODE", "auto").strip().lower(),
        blender_bin=_native_binary("BLENDER_BIN", "blender", "blender-*-windows-x64/blender.exe", "Blender Foundation/Blender 5.2/blender.exe"),
        blender_timeout_seconds=int(os.getenv("BLENDER_TIMEOUT_SECONDS", "1800")),
        openusd_generate_usdc=_bool("OPENUSD_GENERATE_USDC", True),
        public_storage_prefix=os.getenv("PUBLIC_STORAGE_PREFIX", "/storage").rstrip("/"),
        speech_mode=os.getenv("SPEECH_MODE", "mock").strip().lower(),
        whisper_model=os.getenv("WHISPER_MODEL", "large-v3-turbo"),
        whisper_model_cache=Path(os.getenv("WHISPER_MODEL_CACHE", root / "storage" / "models" / "whisper")),
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
