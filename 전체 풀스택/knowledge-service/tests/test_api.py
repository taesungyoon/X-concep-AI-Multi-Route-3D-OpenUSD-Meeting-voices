import os
os.environ["QDRANT_URL"] = ":memory:"
from fastapi.testclient import TestClient
from app.main import app
client = TestClient(app)

def test_ingest_search():
    r=client.post("/v1/ingest",json={"text":"서보모터와 안전커버를 적용한 FPCB 벤딩 유닛","project_id":"P1"})
    assert r.status_code==200 and r.json()["inserted"]==1
    r=client.post("/v1/search",json={"query":"FPCB 안전커버","limit":3})
    assert r.status_code==200 and len(r.json()["items"])>=1
