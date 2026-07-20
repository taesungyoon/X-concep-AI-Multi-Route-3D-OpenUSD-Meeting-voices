# 주요 API

- `POST /api/projects`: 텍스트+이미지 입력 및 2D 생성함
- `GET /api/projects`: 이력 조회함
- `POST /api/projects/{id}/generate-3d`: 선택 2D로 3D/OpenUSD 생성함
- `POST /api/meetings`: 회의 프로젝트 생성함
- `POST /api/projects/{id}/meeting/chunks`: 음성 청크 전사함
- `POST /api/projects/{id}/meeting/analyze`: 회의 요구사항 분석함
- `POST /api/projects/{id}/meeting/generate-2d`: 회의 기준 2D 생성함
- `POST /api/projects/{id}/meeting/patch`: 후속 회의 변경 Revision 생성함
- `POST /api/knowledge/ingest`: RAG 청크 저장함
- `POST /api/knowledge/search`: Qdrant 검색함
- `POST /api/vision/events`: DeepStream/Metropolis 이벤트 수신함
