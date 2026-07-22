from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

OutputGoal = Literal["auto", "fast", "structural", "high_quality", "motion_openusd"]
QualityProfile = Literal["preview", "standard", "final"]
EngineOverride = Literal[
    "hunyuan3d",
    "openscad",
    "openscad_auto",
    "openscad_part",
    "openscad_module",
    "openscad_equipment",
    "blender",
    "hybrid",
]
ValidationGrade = Literal[
    "concept",
    "structured",
    "validated",
    "engineer_reviewed",
    "manufacturing_approved",
]


class Generate2DRequest(BaseModel):
    project_id: str = Field(pattern=r"^[A-Za-z0-9-]+$")
    prompt: str = Field(min_length=8, max_length=4000)
    category: str = Field(pattern=r"^(equipment|module|part)$")
    image_paths: list[str] = Field(default_factory=list, max_length=4)
    meeting_analysis: dict[str, Any] | None = None


class Generate3DRequest(BaseModel):
    project_id: str = Field(pattern=r"^[A-Za-z0-9-]+$")
    prompt: str = Field(min_length=8, max_length=4000)
    category: str = Field(pattern=r"^(equipment|module|part)$")
    selected_2d_id: str
    selected_image_path: str = ""
    meeting_analysis: dict[str, Any] | None = None
    source_analysis: dict[str, Any] | None = None
    revision: int = Field(default=1, ge=1)
    output_goal: OutputGoal = "auto"
    quality_profile: QualityProfile = "standard"
    engine_override: EngineOverride | None = None
    previous_design_state: dict[str, Any] | None = None
    previous_geometry_contract: dict[str, Any] | None = None
    regeneration_scope: list[str] = Field(default_factory=list, max_length=32)
    regeneration_reason: str = Field(default="", max_length=500)


class ReviewGradeRequest(BaseModel):
    project_id: str = Field(pattern=r"^[A-Za-z0-9-]+$")
    requested_grade: Literal["engineer_reviewed", "manufacturing_approved"]
    reviewer: str = Field(min_length=2, max_length=120)
    note: str = Field(default="", max_length=2000)


class MeetingTranscribeRequest(BaseModel):
    project_id: str = Field(pattern=r"^[A-Za-z0-9-]+$")
    audio_path: str
    chunk_index: int = Field(default=0, ge=0)
    language: str = "ko"


class TranscriptSegment(BaseModel):
    start: float = 0
    end: float = 0
    speaker: str = "unknown"
    text: str
    confidence: float = 0.8


class MeetingAnalyzeRequest(BaseModel):
    project_id: str = Field(pattern=r"^[A-Za-z0-9-]+$")
    category: str = Field(default="equipment", pattern=r"^(equipment|module|part)$")
    transcript: str = Field(min_length=2, max_length=30000)
    segments: list[TranscriptSegment] = Field(default_factory=list)
    previous_analysis: dict[str, Any] | None = None
    reference_image_paths: list[str] = Field(default_factory=list, max_length=4)
    retrieval_context: list[dict[str, Any]] = Field(default_factory=list)


class MeetingPatchRequest(BaseModel):
    project_id: str = Field(pattern=r"^[A-Za-z0-9-]+$")
    base_revision: int = Field(default=1, ge=1)
    transcript: str = Field(min_length=2, max_length=30000)
    current_analysis: dict[str, Any]
