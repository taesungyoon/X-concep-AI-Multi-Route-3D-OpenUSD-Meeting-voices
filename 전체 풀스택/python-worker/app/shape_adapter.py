from __future__ import annotations

import asyncio
import base64
import io
import os
import uuid
from typing import Any

import httpx
from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import Response
from PIL import Image
from pydantic import BaseModel

app = FastAPI(title="ComfyUI Hunyuan3D adapter")
COMFYUI_BASE_URL = os.getenv("COMFYUI_BASE_URL", "http://comfyui:8188").rstrip("/")
SHAPE_API_KEY = os.getenv("SHAPE_API_KEY", "")
MODEL = os.getenv("HUNYUAN_MODEL", "tencent/Hunyuan3D-2.1/hunyuan3d-dit-v2-1")
STEPS = int(os.getenv("HUNYUAN_STEPS", "80"))
TIMEOUT = float(os.getenv("SHAPE_TIMEOUT_SECONDS", "1800"))


class GenerateRequest(BaseModel):
    image: str
    remove_background: bool = True
    type: str = "glb"


def _authorize(authorization: str | None) -> None:
    if SHAPE_API_KEY and authorization != f"Bearer {SHAPE_API_KEY}":
        raise HTTPException(status_code=401, detail="invalid bearer token")


def _rgba_image(encoded: str) -> bytes:
    try:
        image = Image.open(io.BytesIO(base64.b64decode(encoded, validate=True))).convert("RGBA")
    except Exception as exc:
        raise HTTPException(status_code=400, detail="invalid base64 image") from exc
    output = io.BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def _prompt(filename: str) -> dict[str, Any]:
    return {
        "1": {"class_type": "LoadImage", "inputs": {"image": filename}},
        "2": {
            "class_type": "Hunyuan3D2ImageTo3D",
            "inputs": {
                "image": ["1", 0],
                "mask": ["1", 1],
                "steps": STEPS,
                "paint": False,
                "face_reducer": False,
                "face_remover": True,
                "floater_remover": True,
                "model": MODEL,
            },
        },
        "3": {"class_type": "Preview3D", "inputs": {"model_file": ["2", 0]}},
    }


@app.get("/health")
async def health() -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.get(f"{COMFYUI_BASE_URL}/object_info/Hunyuan3D2ImageTo3D")
    if response.status_code != 200:
        raise HTTPException(status_code=503, detail="Hunyuan3D node unavailable")
    return {"ok": True, "model": MODEL}


@app.post("/generate")
async def generate(request: GenerateRequest, authorization: str | None = Header(default=None)) -> Response:
    _authorize(authorization)
    if request.type != "glb":
        raise HTTPException(status_code=400, detail="only glb output is supported")
    filename = f"shape-{uuid.uuid4().hex}.png"
    timeout = httpx.Timeout(TIMEOUT, connect=30)
    async with httpx.AsyncClient(timeout=timeout) as client:
        upload = await client.post(
            f"{COMFYUI_BASE_URL}/upload/image",
            files={"image": (filename, _rgba_image(request.image), "image/png")},
            data={"type": "input", "overwrite": "true"},
        )
        upload.raise_for_status()
        queued = await client.post(f"{COMFYUI_BASE_URL}/prompt", json={"prompt": _prompt(filename)})
        queued.raise_for_status()
        prompt_id = queued.json()["prompt_id"]
        while True:
            history_response = await client.get(f"{COMFYUI_BASE_URL}/history/{prompt_id}")
            history_response.raise_for_status()
            history = history_response.json().get(prompt_id)
            if history:
                status = history.get("status", {})
                if status.get("status_str") == "error":
                    messages = status.get("messages", [])
                    detail = messages[-1][1].get("exception_message", "generation failed") if messages else "generation failed"
                    raise HTTPException(status_code=502, detail=detail)
                result = history.get("outputs", {}).get("3", {}).get("result")
                if status.get("completed") and result:
                    model = await client.get(f"{COMFYUI_BASE_URL}/view", params={"filename": result[0], "type": "output"})
                    model.raise_for_status()
                    if model.content[:4] != b"glTF":
                        raise HTTPException(status_code=502, detail="ComfyUI returned invalid GLB")
                    return Response(model.content, media_type="model/gltf-binary")
            await asyncio.sleep(1)
