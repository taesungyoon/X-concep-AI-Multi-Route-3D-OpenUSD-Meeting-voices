from __future__ import annotations

import base64
import binascii
import io
import os
import sys
import threading
from pathlib import Path

import torch
from fastapi import FastAPI, HTTPException
from fastapi.responses import Response
from PIL import Image
from pydantic import BaseModel, Field


SERVICE_DIR = Path(__file__).resolve().parent
DEFAULT_TRIPOSR_SOURCE = next(
    (parent / ".triposr-src" for parent in SERVICE_DIR.parents if (parent / ".triposr-src").is_dir()),
    SERVICE_DIR.parent / ".triposr-src",
)
TRIPOSR_SOURCE = Path(
    os.getenv("TRIPOSR_SOURCE", str(DEFAULT_TRIPOSR_SOURCE))
).resolve()
if not TRIPOSR_SOURCE.is_dir():
    raise RuntimeError(f"TripoSR source directory is missing: {TRIPOSR_SOURCE}")
sys.path.insert(0, str(TRIPOSR_SOURCE))
sys.path.insert(0, str(SERVICE_DIR))

from tsr.system import TSR
from tsr.utils import remove_background, resize_foreground


class GenerateRequest(BaseModel):
    image: str = Field(min_length=8)
    remove_background: bool = True
    foreground_ratio: float = Field(default=0.85, ge=0.5, le=1.0)
    mc_resolution: int | None = Field(default=None, ge=64, le=512)
    type: str = Field(default="glb", pattern="^glb$")


class TripoSREngine:
    def __init__(self) -> None:
        self.device = os.getenv(
            "TRIPOSR_DEVICE", "cuda:0" if torch.cuda.is_available() else "cpu"
        )
        self.model_name = os.getenv("TRIPOSR_MODEL", "stabilityai/TripoSR")
        self.chunk_size = int(os.getenv("TRIPOSR_CHUNK_SIZE", "8192"))
        self.default_resolution = int(os.getenv("TRIPOSR_MC_RESOLUTION", "256"))
        self._model = None
        self._rembg_session = None
        self._lock = threading.Lock()

    @property
    def loaded(self) -> bool:
        return self._model is not None

    def load(self) -> None:
        if self._model is not None:
            return
        model = TSR.from_pretrained(
            self.model_name, config_name="config.yaml", weight_name="model.ckpt"
        )
        model.renderer.set_chunk_size(self.chunk_size)
        model.to(self.device)
        model.eval()
        self._model = model

    def generate(self, image: Image.Image, *, remove_bg: bool, ratio: float, resolution: int) -> bytes:
        with self._lock:
            self.load()
            if remove_bg:
                if self._rembg_session is None:
                    import rembg
                    self._rembg_session = rembg.new_session()
                image = remove_background(image, self._rembg_session)
            elif image.mode != "RGBA":
                image = image.convert("RGBA")
            image = resize_foreground(image, ratio)
            background = Image.new("RGBA", image.size, (128, 128, 128, 255))
            background.alpha_composite(image)
            prepared = background.convert("RGB")
            with torch.inference_mode():
                scene_codes = self._model([prepared], device=self.device)
                mesh = self._model.extract_mesh(
                    scene_codes, True, resolution=resolution
                )[0]
            payload = mesh.export(file_type="glb")
            if not isinstance(payload, bytes):
                raise RuntimeError("TripoSR GLB exporter returned a non-binary payload")
            if not payload.startswith(b"glTF"):
                raise RuntimeError("TripoSR did not produce a binary GLB")
            return payload


engine = TripoSREngine()
app = FastAPI(title="X-concep TripoSR service", version="1.0")


@app.get("/health")
def health():
    return {
        "status": "ok",
        "engine": "triposr",
        "loaded": engine.loaded,
        "device": engine.device,
        "cuda": torch.cuda.is_available(),
        "model": engine.model_name,
    }


@app.post("/generate")
def generate(request: GenerateRequest):
    try:
        raw = base64.b64decode(request.image, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise HTTPException(status_code=400, detail="invalid base64 image") from exc
    if len(raw) > 32 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="image exceeds 32 MiB")
    try:
        with Image.open(io.BytesIO(raw)) as opened:
            image = opened.convert("RGBA")
            image.load()
    except Exception as exc:
        raise HTTPException(status_code=400, detail="invalid image") from exc
    try:
        payload = engine.generate(
            image,
            remove_bg=request.remove_background,
            ratio=request.foreground_ratio,
            resolution=request.mc_resolution or engine.default_resolution,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"TripoSR generation failed: {exc}") from exc
    return Response(payload, media_type="model/gltf-binary")
