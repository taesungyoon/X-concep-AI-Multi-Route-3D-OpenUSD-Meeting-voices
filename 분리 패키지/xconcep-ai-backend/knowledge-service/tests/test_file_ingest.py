import os
os.environ.setdefault('QDRANT_URL',':memory:')
os.environ.setdefault('NEMO_RETRIEVER_MODE','fallback')
from fastapi.testclient import TestClient
from app.main import app


def test_file_ingest_and_search():
    client=TestClient(app)
    response=client.post('/v1/ingest/file',files={'file':('manual.txt','서보모터 구동 안전커버 설비 폭 900 mm'.encode('utf-8'),'text/plain')},data={'project_id':'PRJ-TEST','metadata_json':'{"source":"unit"}'})
    assert response.status_code==200,response.text
    assert response.json()['inserted']>=1
    found=client.post('/v1/search',json={'query':'서보모터 안전커버','limit':5,'project_id':'PRJ-TEST'})
    assert found.status_code==200
    assert found.json()['items']
