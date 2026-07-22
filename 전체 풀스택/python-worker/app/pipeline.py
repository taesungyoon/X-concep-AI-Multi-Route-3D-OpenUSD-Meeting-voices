from __future__ import annotations

import json
import shutil
import importlib.util
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

import httpx
import trimesh

from . import generator as generator_module
from .blender_engine import generate_blender_asset
from .design_state import build_design_state
from .generation_router import plan_generation
from .generator import generate_3d as generate_3d_mock
from .hunyuan_client import Hunyuan3DClient
from .llm_client import LocalGemmaClient
from .meeting_analyzer import MeetingAnalyzer
from .models import Generate2DRequest, Generate3DRequest, MeetingAnalyzeRequest, MeetingPatchRequest, MeetingTranscribeRequest
from .openai_image_client import GPTImageClient
from .openscad_engine import generate_openscad
from .openusd_exporter import export_openusd, validate_usda
from .parametric_generators import (
    SPECIALIZED_MODES,
    apply_partial_regeneration,
    build_geometry_contract,
)
from .quality_gate import validate_asset
from .renderer import create_preview
from .settings import Settings
from .speech_client import LocalSpeechClient


class GenerationPipeline:
    def __init__(self, settings: Settings):
        self.settings = settings
        generator_module.STORAGE_PATH = settings.storage_path
        self.llm = LocalGemmaClient(settings)
        self.images = GPTImageClient(settings)
        self.hunyuan = Hunyuan3DClient(settings)
        self.speech = LocalSpeechClient(settings)
        self.meeting = MeetingAnalyzer(settings)

    def generate_2d(self, request: Generate2DRequest) -> dict[str, Any]:
        image_paths = [self._resolve_path(value) for value in request.image_paths]
        analysis = self.llm.analyze(request.prompt, request.category, [str(path) for path in image_paths])
        results = self.images.generate_concepts(
            project_id=request.project_id,
            prompt=request.prompt,
            category=request.category,
            image_paths=[str(path) for path in image_paths],
            analysis=analysis,
        )
        project_dir = self._project_dir(request.project_id)
        (project_dir / "analysis.json").write_text(
            json.dumps(analysis, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return {
            "results": results,
            "analysis": analysis,
            "pipeline": {
                "llm": f"OpenAI-compatible ({self.settings.llm_mode})" if self.settings.llm_mode != "mock" else "mock",
                "image": (
                    f"OpenAI {self.settings.openai_image_model}"
                    if self.settings.openai_image_mode == "openai"
                    else f"ComfyUI {self.settings.comfyui_unet_model}"
                    if self.settings.openai_image_mode == "comfyui"
                    else "mock"
                ),
                "external_services": ["OpenAI Image API"] if self.settings.openai_image_mode == "openai" else [],
                "available_3d_routes": [
                    "hunyuan3d", "openscad", "openscad_auto", "openscad_part",
                    "openscad_module", "openscad_equipment", "blender", "hybrid",
                ],
            },
        }

    def generate_3d(self, request: Generate3DRequest) -> dict[str, Any]:
        selected_path = self._resolve_path(request.selected_image_path)
        source_analysis = request.source_analysis or self._load_json(self._project_dir(request.project_id) / "analysis.json")
        design_state = build_design_state(
            project_id=request.project_id,
            revision=request.revision,
            prompt=request.prompt,
            category=request.category,
            selected_2d_id=request.selected_2d_id,
            source_analysis=source_analysis,
            meeting_analysis=request.meeting_analysis,
            previous_design_state=request.previous_design_state,
        )
        plan = plan_generation(
            design_state,
            request.output_goal,
            request.quality_profile,
            request.engine_override,
            selected_path.exists(),
            self.settings.routing_low_confidence,
            self.settings.routing_high_confidence,
        )
        project_dir = self._project_dir(request.project_id)
        result_root = project_dir / "result"
        result_root.mkdir(parents=True, exist_ok=True)
        (project_dir / "design_state.json").write_text(json.dumps(design_state, ensure_ascii=False, indent=2), encoding="utf-8")
        (project_dir / "generation_plan.json").write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")

        route = str(plan["primary_route"])
        source_assets: list[dict[str, Any]] = []
        source_glbs: list[Path] = []
        active_asset: dict[str, Any]

        if route in {"hunyuan3d", "hybrid"} or "hunyuan3d" in plan.get("secondary_routes", []):
            hunyuan_asset = self._generate_hunyuan(request, selected_path, result_root / "fast")
            source_assets.append(hunyuan_asset)
            source_glbs.append(Path(hunyuan_asset["absolute_paths"]["glb"]))

        if route in {"openscad", "hybrid"} or "openscad" in plan.get("secondary_routes", []):
            generator_mode = str(plan.get("generator_mode") or "openscad")
            geometry_contract: dict[str, Any] | None = None
            if generator_mode in SPECIALIZED_MODES:
                candidate_contract = build_geometry_contract(
                    design_state,
                    request.category,
                    generator_mode,
                )
                if request.regeneration_scope:
                    if not request.previous_geometry_contract:
                        raise ValueError("부분 재생성에 필요한 기존 GeometryContract가 없음")
                    geometry_contract = apply_partial_regeneration(
                        request.previous_geometry_contract,
                        candidate_contract,
                        request.regeneration_scope,
                    )
                else:
                    geometry_contract = candidate_contract
            openscad_asset = self._generate_openscad(
                request,
                design_state,
                result_root / "structural",
                generator_mode=generator_mode,
                geometry_contract=geometry_contract,
            )
            source_assets.append(openscad_asset)
            source_glbs.append(Path(openscad_asset["absolute_paths"]["glb"]))

        if not source_assets:
            raise RuntimeError("실행 가능한 3D 생성 경로가 없음")

        blender_required = "blender" in plan.get("postprocess", [])
        if blender_required:
            blender_asset = self._generate_blender(
                request=request,
                design_state=design_state,
                selected_path=selected_path,
                source_glbs=source_glbs,
                output_dir=result_root / "high_quality",
            )
            source_assets.append(blender_asset)
            active_asset = blender_asset
        else:
            if route == "openscad":
                active_asset = next(item for item in source_assets if item["route_key"] == "structural")
            else:
                active_asset = next(item for item in source_assets if item["route_key"] == "fast")

        openusd_required = "openusd" in plan.get("postprocess", []) or request.output_goal == "motion_openusd"
        structural_asset = next((item for item in source_assets if item.get("route_key") == "structural"), None)
        active_glb = Path(active_asset["absolute_paths"]["glb"])
        manifest_path = Path(active_asset["absolute_paths"]["manifest"]) if active_asset["absolute_paths"].get("manifest") else None
        validation = validate_asset(
            glb_path=active_glb,
            route=route,
            design_state=design_state,
            manifest_path=manifest_path,
            dimension_tolerance_pct=self.settings.validation_dimension_tolerance_pct,
            blender_processed=active_asset["route_key"] == "high_quality",
        )
        if structural_asset and validation.get("multiview"):
            view_urls = structural_asset.get("validation_views") or {}
            for view_name, view in (validation["multiview"].get("views") or {}).items():
                if view_name in view_urls:
                    view["url"] = view_urls[view_name]
            validation["multiview"]["report_url"] = structural_asset.get("multiview_report_url")
        design_state["validation_grade"] = validation["grade"]
        design_state["validation_scope"] = validation["usage_scope"]
        (project_dir / "design_state.json").write_text(json.dumps(design_state, ensure_ascii=False, indent=2), encoding="utf-8")
        (result_root / "validation_report.json").write_text(json.dumps(validation, ensure_ascii=False, indent=2), encoding="utf-8")
        assembly_contract: dict[str, Any] = {}
        if structural_asset:
            geometry_path = structural_asset.get("absolute_paths", {}).get("geometry_json")
            if geometry_path:
                assembly_contract = self._load_json(Path(str(geometry_path)))
        openusd = self._package_openusd(
            request=request,
            design_state=design_state,
            plan=plan,
            active_asset=active_asset,
            assembly_contract=assembly_contract,
            output_dir=result_root,
            required=openusd_required,
        )

        assets_by_key = {item["route_key"]: self._without_absolute_paths(item) for item in source_assets}
        result = {
            "title": active_asset["title"],
            "route_key": active_asset["route_key"],
            "active_asset": active_asset["route_key"],
            "glb_url": active_asset.get("glb_url"),
            "stl_url": active_asset.get("stl_url"),
            "preview_url": active_asset.get("preview_url"),
            "scad_url": active_asset.get("scad_url"),
            "geometry_json_url": active_asset.get("geometry_json_url"),
            "blender_script_url": active_asset.get("blender_script_url"),
            "material_manifest_url": active_asset.get("material_manifest_url"),
            "tags": active_asset.get("tags", []),
            "provider": active_asset.get("provider", {}),
            "assets": assets_by_key,
            "design_state": design_state,
            "generation_plan": plan,
            "generator_mode": plan.get("generator_mode"),
            "geometry_contract": assembly_contract,
            "partial_regeneration": assembly_contract.get("partial_regeneration"),
            "validation_views": (structural_asset or {}).get("validation_views") or {},
            "multiview_report_url": (structural_asset or {}).get("multiview_report_url"),
            "validation": validation,
            "validation_grade": validation["grade"],
            "validation_grade_label": validation["grade_label"],
            "regeneration_actions": plan.get("user_actions", []),
            "openusd": openusd,
            "omniverse": {
                "enabled": self.settings.omniverse_enabled,
                "nucleus_url": self.settings.omniverse_nucleus_url or None,
                "stream_url": self.settings.omniverse_stream_url or None,
                "physics_ready": self.settings.omniverse_enable_physics,
                "variants": self.settings.omniverse_enable_variants,
                "kit_app": "xconcep.meeting.review",
                "asset_source": "blender" if active_asset["route_key"] == "high_quality" else active_asset["route_key"],
            },
            "absolute_paths": active_asset.get("absolute_paths", {}),
        }
        if openusd:
            result["absolute_paths"].update(openusd.get("absolute_paths") or {})
            result.update({
                "usda_url": openusd.get("usda_url"),
                "usdc_url": openusd.get("usdc_url"),
                "openusd_root_url": openusd.get("root_url"),
                "openusd_manifest_url": openusd.get("manifest_url"),
                "openusd_validation": openusd.get("validation"),
                "openusd_package_validation": openusd.get("package_validation"),
                "openusd_layers": openusd.get("layers"),
            })
        return result

    def _generate_hunyuan(self, request: Generate3DRequest, selected_path: Path, output_dir: Path) -> dict[str, Any]:
        output_dir.mkdir(parents=True, exist_ok=True)
        glb_path = output_dir / "model_fast.glb"
        stl_path = output_dir / "model_fast.stl"
        preview_path = output_dir / "render_fast.png"
        if self.settings.hunyuan_mode == "mock":
            mock = generate_3d_mock(request.project_id, request.prompt, request.category, request.selected_2d_id)
            mock_glb = Path(mock["absolute_paths"]["glb"])
            mock_stl = Path(mock["absolute_paths"]["stl"])
            mock_preview = Path(mock["absolute_paths"]["preview"])
            shutil.copy2(mock_glb, glb_path)
            shutil.copy2(mock_stl, stl_path)
            shutil.copy2(mock_preview, preview_path)
            provider = {"mode": "mock", "engine": self.settings.shape_provider}
        else:
            provider = self.hunyuan.generate(selected_path, glb_path)
            self._glb_to_stl(glb_path, stl_path)
            create_preview(glb_path, selected_path, preview_path, self.settings.blender_bin)
        return {
            "route_key": "fast",
            "title": "빠른 이미지 기반 3D",
            "glb_url": self._public_url(request.project_id, "result/fast/model_fast.glb"),
            "stl_url": self._public_url(request.project_id, "result/fast/model_fast.stl"),
            "preview_url": self._public_url(request.project_id, "result/fast/render_fast.png"),
            "tags": ["빠른 3D", self.settings.shape_provider, "Mesh", "GLB", "STL"],
            "provider": provider,
            "usage_scope": ["빠른 외형 확인", "웹 3D 검토", "Blender 후처리 기초 Mesh"],
            "absolute_paths": {"glb": str(glb_path), "stl": str(stl_path), "preview": str(preview_path)},
        }

    def _generate_openscad(
        self,
        request: Generate3DRequest,
        design_state: dict[str, Any],
        output_dir: Path,
        *,
        generator_mode: str,
        geometry_contract: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        generated = generate_openscad(
            design_state=design_state,
            category=request.category,
            output_dir=output_dir,
            openscad_bin=self.settings.openscad_bin,
            timeout_seconds=self.settings.openscad_timeout_seconds,
            mode=self.settings.openscad_mode,
            generator_mode=generator_mode,
            geometry_contract=geometry_contract,
        )
        labels = {
            "openscad": "범용 OpenSCAD 구조 3D",
            "openscad_part": "부품 파라메트릭 3D",
            "openscad_module": "모듈 파라메트릭 3D",
            "openscad_equipment": "설비 파라메트릭 3D",
        }
        return {
            "route_key": "structural",
            "title": labels.get(generator_mode, "치수·구조 기반 3D"),
            "glb_url": self._public_url(request.project_id, "result/structural/model_structural.glb"),
            "stl_url": self._public_url(request.project_id, "result/structural/model_structural.stl"),
            "preview_url": self._public_url(request.project_id, "result/structural/render_structural.png"),
            "scad_url": self._public_url(request.project_id, "result/structural/model.scad"),
            "geometry_json_url": self._public_url(request.project_id, "result/structural/geometry.json"),
            "manifest_url": self._public_url(request.project_id, "result/structural/assembly_manifest.json"),
            "multiview_report_url": self._public_url(request.project_id, "result/structural/multiview_validation.json"),
            "validation_views": {
                view_name: self._public_url(request.project_id, f"result/structural/views/{view_name}.png")
                for view_name in ("front", "top", "right")
            } if generator_mode in SPECIALIZED_MODES else {},
            "tags": ["구조 중심 3D", "OpenSCAD", generator_mode, "Parametric", "SCAD", "STL"],
            "generator_mode": generator_mode,
            "provider": generated.provider,
            "usage_scope": ["구조·배치 검토", "초기 엔지니어링", "후속 CAD 입력"],
            "absolute_paths": {
                "glb": str(generated.glb_path), "stl": str(generated.stl_path), "preview": str(generated.preview_path),
                "scad": str(generated.scad_path), "manifest": str(generated.manifest_path), "geometry_json": str(generated.geometry_json_path),
                "multiview_report": str(output_dir / "multiview_validation.json") if generator_mode in SPECIALIZED_MODES else None,
                "view_front": str(output_dir / "views" / "front.png") if generator_mode in SPECIALIZED_MODES else None,
                "view_top": str(output_dir / "views" / "top.png") if generator_mode in SPECIALIZED_MODES else None,
                "view_right": str(output_dir / "views" / "right.png") if generator_mode in SPECIALIZED_MODES else None,
            },
        }

    def _generate_blender(
        self,
        *,
        request: Generate3DRequest,
        design_state: dict[str, Any],
        selected_path: Path,
        source_glbs: list[Path],
        output_dir: Path,
    ) -> dict[str, Any]:
        generated = generate_blender_asset(
            source_glbs=source_glbs,
            selected_image_path=selected_path,
            output_dir=output_dir,
            blender_bin=self.settings.blender_bin,
            timeout_seconds=self.settings.blender_timeout_seconds,
            mode=self.settings.blender_mode,
            profile=request.quality_profile,
            design_state=design_state,
        )
        result = {
            "route_key": "high_quality",
            "title": "고품질 조립·렌더링 3D",
            "glb_url": self._public_url(request.project_id, "result/high_quality/model_high_quality.glb"),
            "preview_url": self._public_url(request.project_id, "result/high_quality/render_high_quality.png"),
            "blender_script_url": self._public_url(request.project_id, "result/high_quality/blender_scene.py"),
            "material_manifest_url": self._public_url(request.project_id, "result/high_quality/material_manifest.json"),
            "tags": ["고품질 3D", "Blender", "PBR", request.quality_profile, "GLB"],
            "provider": generated["provider"],
            "usage_scope": ["통합 Assembly", "고품질 렌더링", "OpenUSD·Omniverse 자산 준비"],
            "absolute_paths": {
                "glb": str(generated["glb_path"]), "preview": str(generated["preview_path"]),
                "blender_script": str(generated["script_path"]), "material_manifest": str(generated["materials_path"]),
            },
        }
        if generated.get("usd_path"):
            result["blender_usd_url"] = self._public_url(request.project_id, "result/high_quality/model_blender.usdc")
            result["absolute_paths"]["blender_usd"] = str(generated["usd_path"])
        if generated.get("blend_path"):
            result["blend_url"] = self._public_url(request.project_id, "result/high_quality/model_high_quality.blend")
            result["absolute_paths"]["blend"] = str(generated["blend_path"])
        return result

    def _package_openusd(
        self,
        *,
        request: Generate3DRequest,
        design_state: dict[str, Any],
        plan: dict[str, Any],
        active_asset: dict[str, Any],
        assembly_contract: dict[str, Any],
        output_dir: Path,
        required: bool,
    ) -> dict[str, Any] | None:
        glb_path = Path(active_asset["absolute_paths"]["glb"])
        output_dir.mkdir(parents=True, exist_ok=True)
        usd_paths = export_openusd(
            glb_path=glb_path,
            output_dir=output_dir,
            metadata={
                "project_id": request.project_id,
                "category": request.category,
                "selected_concept_id": request.selected_2d_id,
                "design_id": design_state.get("design_id"),
                "generation_route": plan.get("primary_route"),
                "generator_mode": plan.get("generator_mode"),
                "validation_grade": design_state.get("validation_grade", "concept"),
                "geometry_contract": assembly_contract,
            },
            generate_usdc=self.settings.openusd_generate_usdc,
            meeting_analysis=request.meeting_analysis,
            revision=request.revision,
            enable_physics=self.settings.omniverse_enable_physics,
            enable_variants=self.settings.omniverse_enable_variants,
            generate_layers=self.settings.omniverse_generate_layers,
            source_usd_path=(Path(active_asset["absolute_paths"]["blender_usd"]) if active_asset.get("absolute_paths", {}).get("blender_usd") else None),
        )
        usda_path = Path(str(usd_paths["usda"]))
        result: dict[str, Any] = {
            "usda_url": self._public_url(request.project_id, "result/model.usda"),
            "usdc_url": self._public_url(request.project_id, "result/model.usdc") if usd_paths.get("usdc") else None,
            "validation": validate_usda(usda_path),
            "absolute_paths": {"usda": str(usda_path)},
        }
        if usd_paths.get("usdc"):
            result["absolute_paths"]["usdc"] = str(usd_paths["usdc"])
        if usd_paths.get("layers"):
            layers = {}
            for key, value in usd_paths["layers"].items():
                relative = Path(value).relative_to(output_dir / "openusd").as_posix()
                layers[key] = self._public_url(request.project_id, "result/openusd/" + relative)
            result["layers"] = layers
            result["root_url"] = layers.get("root")
            root_stage = Path(str(usd_paths["layers"].get("root", "")))
            if root_stage.is_file():
                result["package_validation"] = validate_usda(root_stage)
        if usd_paths.get("manifest"):
            result["manifest_url"] = self._public_url(request.project_id, "result/openusd/manifest.json")
        return result

    def transcribe_meeting(self, request: MeetingTranscribeRequest) -> dict[str, Any]:
        audio_path = self._resolve_path(request.audio_path)
        result = self.speech.transcribe(audio_path, request.language, request.chunk_index)
        result["chunk_index"] = request.chunk_index
        return result

    def analyze_meeting(self, request: MeetingAnalyzeRequest) -> dict[str, Any]:
        analysis = self.meeting.analyze(request.transcript, request.category, request.previous_analysis, request.retrieval_context)
        project_dir = self._project_dir(request.project_id)
        meeting_dir = project_dir / "meeting"
        meeting_dir.mkdir(parents=True, exist_ok=True)
        (meeting_dir / "analysis.json").write_text(json.dumps(analysis, ensure_ascii=False, indent=2), encoding="utf-8")
        return {"analysis": analysis, "generation_prompt": analysis.get("generation_prompt", request.transcript)}

    def patch_meeting(self, request: MeetingPatchRequest) -> dict[str, Any]:
        patch = self.meeting.create_patch(request.transcript, request.current_analysis, request.base_revision)
        project_dir = self._project_dir(request.project_id)
        meeting_dir = project_dir / "meeting"
        meeting_dir.mkdir(parents=True, exist_ok=True)
        (meeting_dir / f"revision-{patch['next_revision']:03d}.json").write_text(
            json.dumps(patch, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return patch

    def health(self) -> dict[str, Any]:
        llm_connected = self._probe_http(self.settings.vllm_base_url, "/models") if self.settings.llm_mode != "mock" else False
        hunyuan_connected = self._probe_http(self.settings.hunyuan_api_url, "/health") if self.settings.hunyuan_mode != "mock" else False
        if self.settings.speech_mode == "nvidia_nim":
            speech_connected = self._probe_http(self.settings.nvidia_asr_url, "/health/ready")
        elif self.settings.speech_mode == "faster_whisper":
            speech_connected = importlib.util.find_spec("faster_whisper") is not None
        elif self.settings.speech_mode == "nemo_asr":
            speech_connected = importlib.util.find_spec("nemo") is not None
        else:
            speech_connected = False
        image_connected = (
            self._probe_http(self.settings.comfyui_base_url, "/system_stats")
            if self.settings.openai_image_mode == "comfyui"
            else None
        )
        image_configured = (
            image_connected
            if self.settings.openai_image_mode == "comfyui"
            else self.settings.openai_image_mode == "openai" and bool(self.settings.openai_api_key)
        )
        image_usage = self.images.usage.today() if self.settings.openai_image_mode == "openai" else None
        openscad_binary = shutil.which(self.settings.openscad_bin)
        blender_binary = shutil.which(self.settings.blender_bin)
        live_3d = hunyuan_connected or bool(openscad_binary) or bool(blender_binary)
        runtime_ready = llm_connected and image_configured and live_3d
        if runtime_ready:
            execution_profile = "live"
        elif any([llm_connected,image_configured,hunyuan_connected,openscad_binary,blender_binary,speech_connected]):
            execution_profile = "partial"
        else:
            execution_profile = "mock"
        return {
            "status": "ok",
            "service": "python-worker",
            "pipeline_mode": self.settings.pipeline_mode,
            "execution_profile": execution_profile,
            "runtime_ready": runtime_ready,
            "llm": {"mode": self.settings.llm_mode, "backend": "OpenAI-compatible" if self.settings.llm_mode != "mock" else "mock", "endpoint": self.settings.vllm_base_url, "model": self.settings.gemma_model_name, "connected": llm_connected},
            "image": {
                "mode": self.settings.openai_image_mode,
                "model": self.settings.comfyui_unet_model if self.settings.openai_image_mode == "comfyui" else self.settings.openai_image_model,
                "endpoint": self.settings.comfyui_base_url if self.settings.openai_image_mode == "comfyui" else None,
                "external": self.settings.openai_image_mode == "openai",
                "configured": bool(image_configured),
                "connected": image_connected,
                "usage_today": image_usage,
                "guardrails": {
                    "max_requests_per_day": self.settings.openai_image_max_requests_per_day,
                    "estimated_cost_usd_per_image": self.settings.openai_image_estimated_cost_usd,
                    "max_estimated_cost_usd_per_day": self.settings.openai_image_max_estimated_cost_usd_per_day,
                } if self.settings.openai_image_mode == "openai" else None,
            },
            "image_to_3d": {"mode": self.settings.hunyuan_mode, "provider": self.settings.shape_provider, "endpoint": self.settings.hunyuan_api_url, "role": "fast_or_freeform_mesh", "connected": hunyuan_connected, "route_alias": "hunyuan3d"},
            "openscad": {"mode": self.settings.openscad_mode, "binary": openscad_binary, "available": bool(openscad_binary), "role": "parametric_structure"},
            "blender": {"mode": self.settings.blender_mode, "binary": blender_binary, "available": bool(blender_binary), "role": "assembly_render_usd_bridge"},
            "routing": {"enabled": True, "low_confidence": self.settings.routing_low_confidence, "high_confidence": self.settings.routing_high_confidence},
            "speech": {"mode": self.settings.speech_mode, "model": self.settings.whisper_model if self.settings.speech_mode == "faster_whisper" else self.settings.speech_mode, "local": True, "connected": speech_connected},
            "omniverse": {
                "enabled": self.settings.omniverse_enabled,
                "nucleus_url": self.settings.omniverse_nucleus_url or None,
                "stream_url": self.settings.omniverse_stream_url or None,
                "kit": False,
                "webrtc": bool(self.settings.omniverse_stream_url),
                "physx": self.settings.omniverse_enable_physics,
                "variants": self.settings.omniverse_enable_variants,
                "asset_validator": False,
                "asset_converter": False,
            },
            "openusd": {"enabled": True, "usdc_requested": self.settings.openusd_generate_usdc, "layered_package": self.settings.omniverse_generate_layers},
        }

    @staticmethod
    def _probe_http(base_url: str, path: str) -> bool:
        try:
            with httpx.Client(timeout=1.5) as client:
                response = client.get(base_url.rstrip("/") + path)
                return response.status_code < 500
        except Exception:
            return False

    def _glb_to_stl(self, glb_path: Path, stl_path: Path) -> None:
        scene = trimesh.load(glb_path, force="scene")
        meshes = []
        if isinstance(scene, trimesh.Scene):
            for node in scene.graph.nodes_geometry:
                transform, geom_name = scene.graph.get(node)
                mesh = scene.geometry[geom_name].copy()
                mesh.apply_transform(transform)
                if isinstance(mesh, trimesh.Trimesh):
                    meshes.append(mesh)
        elif isinstance(scene, trimesh.Trimesh):
            meshes.append(scene)
        if not meshes:
            raise RuntimeError("GLB 결과에서 메시를 찾을 수 없음")
        trimesh.util.concatenate(meshes).export(stl_path)

    def _project_dir(self, project_id: str) -> Path:
        path = self.settings.storage_path / "projects" / project_id
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _resolve_path(self, value: str) -> Path:
        root = self.settings.storage_path.resolve()
        if not value:
            return root / "__missing__"
        cleaned = value.replace("\\", "/")
        if cleaned.startswith("/storage/"):
            cleaned = cleaned[len("/storage/"):]
            candidate = (root / cleaned).resolve()
        elif cleaned.startswith("storage/"):
            cleaned = cleaned[len("storage/"):]
            candidate = (root / cleaned).resolve()
        else:
            native_path = Path(value)
            windows_path = PureWindowsPath(value)
            if native_path.is_absolute():
                candidate = native_path.resolve()
            elif PurePosixPath(cleaned).is_absolute() or windows_path.is_absolute() or windows_path.drive:
                raise ValueError("STORAGE_PATH 외부 경로 접근은 허용되지 않음")
            else:
                candidate = (root / cleaned).resolve()
        if candidate != root and root not in candidate.parents:
            raise ValueError("STORAGE_PATH 외부 경로 접근은 허용되지 않음")
        return candidate

    def _public_url(self, project_id: str, relative: str) -> str:
        return f"{self.settings.public_storage_prefix}/projects/{project_id}/{relative}"

    def _load_json(self, path: Path) -> dict[str, Any] | None:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None

    def _without_absolute_paths(self, asset: dict[str, Any]) -> dict[str, Any]:
        return {key: value for key, value in asset.items() if key != "absolute_paths"}
