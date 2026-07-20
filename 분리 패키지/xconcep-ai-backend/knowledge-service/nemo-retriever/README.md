# NeMo Retriever Integration

NeMo Retriever는 문서·이미지·오디오·비디오의 추출/청킹/메타데이터화 계층임. Qdrant는 임베딩 저장·검색 계층임.

본 패키지는 경량 Qdrant 서비스가 기본이며, 운영 환경에서는 다음 환경변수로 NVIDIA Embedding NIM을 연결함.

```env
EMBED_MODE=nim
EMBED_URL=http://embedding-nim:8000
EMBED_MODEL=nvidia/nv-embedqa-e5-v5
```

PDF/도면 대량 인제스트는 NVIDIA NeMo Retriever Library 또는 RAG Blueprint를 별도 프로파일로 배치하고 `/v1/ingest`로 정제된 청크를 전달하도록 설계함.
