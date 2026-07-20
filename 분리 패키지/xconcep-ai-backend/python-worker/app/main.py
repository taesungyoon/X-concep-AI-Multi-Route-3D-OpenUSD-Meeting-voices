from __future__ import annotations

from fastapi import FastAPI, HTTPException

from .models import (
    Generate2DRequest,
    Generate3DRequest,
    MeetingAnalyzeRequest,
    MeetingPatchRequest,
    MeetingTranscribeRequest,
)
from .pipeline import GenerationPipeline
from .settings import get_settings

settings = get_settings()
pipeline = GenerationPipeline(settings)
app = FastAPI(title="X concep Multi-Route 3D + OpenUSD Worker", version="4.0.0")


@app.get("/health")
def health() -> dict:
    return pipeline.health()


@app.post("/v1/generate/2d")
def create_2d(request: Generate2DRequest) -> dict:
    try:
        return pipeline.generate_2d(request)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post("/v1/generate/3d")
def create_3d(request: Generate3DRequest) -> dict:
    try:
        return pipeline.generate_3d(request)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post("/v1/meeting/transcribe")
def transcribe_meeting(request: MeetingTranscribeRequest) -> dict:
    try:
        return pipeline.transcribe_meeting(request)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post("/v1/meeting/analyze")
def analyze_meeting(request: MeetingAnalyzeRequest) -> dict:
    try:
        return pipeline.analyze_meeting(request)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post("/v1/meeting/patch")
def patch_meeting(request: MeetingPatchRequest) -> dict:
    try:
        return pipeline.patch_meeting(request)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
