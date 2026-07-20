from collections.abc import AsyncGenerator
import os
import httpx
from pydantic import Field
from nat.plugin_api import Builder, FunctionGroup, FunctionGroupBaseConfig, register_function_group

class XconcepToolsConfig(FunctionGroupBaseConfig, name='xconcep_tools'):
    worker_url: str = Field(default=os.getenv('PYTHON_WORKER_URL','http://python-worker:8001'))

@register_function_group(config_type=XconcepToolsConfig)
async def xconcep_tools(config:XconcepToolsConfig, _builder:Builder) -> AsyncGenerator[FunctionGroup,None]:
    group=FunctionGroup(config=config)
    async def _call(path:str,payload:dict)->dict:
        async with httpx.AsyncClient(timeout=3600) as c:
            r=await c.post(config.worker_url.rstrip('/')+path,json=payload); r.raise_for_status(); return r.json()
    async def analyze_requirements(payload:dict)->dict: return await _call('/v1/meeting/analyze',payload)
    async def generate_2d(payload:dict)->dict: return await _call('/v1/generate/2d',payload)
    async def generate_3d(payload:dict)->dict: return await _call('/v1/generate/3d',payload)
    async def transcribe_meeting(payload:dict)->dict: return await _call('/v1/meeting/transcribe',payload)
    async def patch_requirements(payload:dict)->dict: return await _call('/v1/meeting/patch',payload)
    for name,fn,desc in [
        ('analyze_requirements',analyze_requirements,'Analyze meeting or prompt requirements into structured manufacturing intent.'),
        ('generate_2d',generate_2d,'Generate four 2D concept options.'),('generate_3d',generate_3d,'Generate local 3D and OpenUSD assets.'),
        ('transcribe_meeting',transcribe_meeting,'Transcribe a local meeting audio chunk.'),('patch_requirements',patch_requirements,'Create a revision patch from new meeting content.')]:
        group.add_function(name, fn, description=desc)
    yield group
