"""Project-scoped retrieval memory backed by Qdrant.

Local mode uses deterministic 384-D hash embeddings and a fallback document
extractor. Production can switch to NVIDIA embedding/Retriever endpoints by
environment variables without changing ingest/search request contracts.
"""

from __future__ import annotations

from fastapi import FastAPI, File, Form, UploadFile, HTTPException
from pydantic import BaseModel, Field
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct, Filter, FieldCondition, MatchValue
from pathlib import Path
import os, hashlib, math, uuid, httpx, tempfile, json

from .retriever_adapter import extract_with_nemo_retriever, extract_fallback

app=FastAPI(title='X concep Knowledge Service',version='1.1.0')
# Provider controls: QDRANT_URL selects persistence; EMBED_MODE=nim and
# NEMO_RETRIEVER_MODE=nemo enable external NVIDIA services.
QDRANT=os.getenv('QDRANT_URL','http://qdrant:6333')
COLLECTION=os.getenv('QDRANT_COLLECTION','xconcep_memory')
EMBED_MODE=os.getenv('EMBED_MODE','hash')
EMBED_URL=os.getenv('EMBED_URL','').rstrip('/')
RETRIEVER_MODE=os.getenv('NEMO_RETRIEVER_MODE','fallback')
DIM=int(os.getenv('EMBED_DIM','384'))
client=QdrantClient(':memory:') if QDRANT == ':memory:' else QdrantClient(url=QDRANT,timeout=30)

class Ingest(BaseModel):
    text:str|None=None; project_id:str|None=None; metadata:dict=Field(default_factory=dict); chunks:list[str]=Field(default_factory=list)
class Search(BaseModel):
    query:str; limit:int=5; project_id:str|None=None
class AssetIndex(BaseModel):
    project_id:str; prompt:str=''; analysis:dict=Field(default_factory=dict); result:dict=Field(default_factory=dict)

def ensure_collection():
    if not client.collection_exists(COLLECTION): client.create_collection(COLLECTION,vectors_config=VectorParams(size=DIM,distance=Distance.COSINE))
def hash_embed(text):
    """Provide an offline, repeatable embedding for development and tests."""
    values=[0.0]*DIM
    for token in text.lower().split():
        h=hashlib.sha256(token.encode()).digest(); idx=int.from_bytes(h[:4],'big')%DIM; values[idx]+=1.0 if h[4]%2 else -1.0
    norm=math.sqrt(sum(v*v for v in values)) or 1.0
    return [v/norm for v in values]
def embed(text):
    """Use NIM embeddings when configured, otherwise stay fully local."""
    if EMBED_MODE=='nim' and EMBED_URL:
        with httpx.Client(timeout=120) as c:
            r=c.post(EMBED_URL+'/v1/embeddings',json={'input':[text],'model':os.getenv('EMBED_MODEL','nvidia/nv-embedqa-e5-v5')}); r.raise_for_status(); return r.json()['data'][0]['embedding']
    return hash_embed(text)

def add(text,metadata):
    ensure_collection(); point=PointStruct(id=str(uuid.uuid4()),vector=embed(text),payload={'text':text,**metadata}); client.upsert(COLLECTION,[point]); return point.id

@app.get('/health')
def health():
    try:
        ensure_collection()
        return {'status':'ok','service':'qdrant-rag','embed_mode':EMBED_MODE,'retriever_mode':RETRIEVER_MODE,'qdrant_collection':COLLECTION}
    except Exception as exc: return {'status':'degraded','service':'qdrant-rag','error':str(exc)}
@app.post('/v1/ingest')
def ingest(req:Ingest):
    texts=req.chunks or ([req.text] if req.text else []); ids=[add(t,{'project_id':req.project_id,**req.metadata}) for t in texts if t and t.strip()]; return {'inserted':len(ids),'ids':ids}
@app.post('/v1/ingest/file')
async def ingest_file(
    file: UploadFile = File(...),
    project_id: str | None = Form(default=None),
    metadata_json: str = Form(default='{}'),
):
    try:
        metadata=json.loads(metadata_json or '{}')
        if not isinstance(metadata,dict): raise ValueError('metadata_json must be object')
    except Exception as exc:
        raise HTTPException(status_code=422,detail=f'metadata_json이 올바르지 않음: {exc}') from exc
    suffix=Path(file.filename or 'document.bin').suffix
    with tempfile.TemporaryDirectory(prefix='xconcep-retriever-') as td:
        path=Path(td)/('source'+suffix)
        total=0
        with path.open('wb') as out:
            while chunk:=await file.read(1024*1024):
                total+=len(chunk)
                if total>100*1024*1024: raise HTTPException(status_code=413,detail='100MB를 초과함')
                out.write(chunk)
        try:
            chunks=extract_with_nemo_retriever(path) if RETRIEVER_MODE=='nemo' else extract_fallback(path)
        except Exception as exc:
            raise HTTPException(status_code=502,detail=str(exc)) from exc
    ids=[add(t,{'project_id':project_id,'source_name':file.filename,'type':'document_chunk',**metadata}) for t in chunks]
    return {'inserted':len(ids),'ids':ids,'extractor':'nemo-retriever' if RETRIEVER_MODE=='nemo' else 'fallback','source_name':file.filename}
@app.post('/v1/search')
def search(req:Search):
    ensure_collection(); query_filter=None
    if req.project_id: query_filter=Filter(must=[FieldCondition(key='project_id',match=MatchValue(value=req.project_id))])
    hits=client.query_points(collection_name=COLLECTION,query=embed(req.query),limit=max(1,min(req.limit,20)),query_filter=query_filter).points
    return {'items':[{'score':h.score,'text':h.payload.get('text',''),'metadata':{k:v for k,v in h.payload.items() if k!='text'}} for h in hits]}
@app.post('/v1/assets/index')
def index_asset(req:AssetIndex):
    text=' '.join([req.prompt,str(req.analysis.get('summary','')),str(req.result.get('title','')),','.join(map(str,req.result.get('tags',[])))])
    pid=add(text,{'project_id':req.project_id,'type':'3d_asset','glb_url':req.result.get('glb_url'),'usda_url':req.result.get('usda_url')}); return {'inserted':1,'id':pid}
