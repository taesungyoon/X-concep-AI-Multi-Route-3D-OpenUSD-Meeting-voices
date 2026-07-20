from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import os, httpx

app=FastAPI(title='X concep NeMo Agent Gateway',version='1.0.0')
WORKER=os.getenv('PYTHON_WORKER_URL','http://python-worker:8001').rstrip('/')
KNOWLEDGE=os.getenv('KNOWLEDGE_SERVICE_URL','http://knowledge-service:8020').rstrip('/')
RUNTIME=os.getenv('AGENT_RUNTIME','fallback')
NAT_SERVER=os.getenv('NAT_SERVER_URL','http://nat-runtime:8011').rstrip('/')

class Payload(BaseModel):
    model_config={'extra':'allow'}

async def post(path,payload,timeout=3600):
    async with httpx.AsyncClient(timeout=timeout) as c:
        r=await c.post(WORKER+path,json=payload); r.raise_for_status(); return r.json()

@app.get('/health')
async def health():
    worker={}
    knowledge={}
    async with httpx.AsyncClient(timeout=10) as c:
        try:
            r=await c.get(WORKER+'/health'); r.raise_for_status(); worker=r.json()
        except Exception as exc: worker={'status':'degraded','error':str(exc)}
        try:
            r=await c.get(KNOWLEDGE+'/health'); r.raise_for_status(); knowledge=r.json()
        except Exception as exc: knowledge={'status':'degraded','error':str(exc)}
    return {'status':'ok','service':'nemo-agent-gateway','runtime':RUNTIME,'nat_profile_available':True,'worker':worker,'knowledge':knowledge}
@app.post('/v1/workflows/generate-2d')
async def generate_2d(p:Payload): return await post('/v1/generate/2d',p.model_dump())
@app.post('/v1/workflows/generate-3d')
async def generate_3d(p:Payload): return await post('/v1/generate/3d',p.model_dump())
@app.post('/v1/workflows/meeting-transcribe')
async def meeting_transcribe(p:Payload): return await post('/v1/meeting/transcribe',p.model_dump(),900)
@app.post('/v1/workflows/meeting-analyze')
async def meeting_analyze(p:Payload): return await post('/v1/meeting/analyze',p.model_dump(),900)
@app.post('/v1/workflows/meeting-patch')
async def meeting_patch(p:Payload): return await post('/v1/meeting/patch',p.model_dump(),900)

@app.post('/v1/workflows/agent-run')
async def agent_run(p:Payload):
    """Execute the installed NeMo Agent Toolkit workflow when the nat profile is active."""
    if RUNTIME != 'nat':
        raise HTTPException(status_code=409,detail='AGENT_RUNTIME=nat 및 nat profile이 필요함')
    async with httpx.AsyncClient(timeout=3600) as c:
        r=await c.post(NAT_SERVER+'/v1/workflow',json=p.model_dump())
        r.raise_for_status()
        return r.json()
