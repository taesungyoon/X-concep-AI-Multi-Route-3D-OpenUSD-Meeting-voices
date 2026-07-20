# X concep AI Multi-Route 주요 API 명세

## 상태

- `GET /health` 서비스 상태임
- `GET /api/system-status` Control Plane·Agent·Worker·Knowledge 통합 상태임

## 프로젝트

### `POST /api/projects`

Multipart Form임.

```text
prompt           필수, 8자 이상
category         equipment | module | part
output_goal      auto | fast | structural | high_quality | motion_openusd
quality_profile  preview | standard | final
images[]         선택, 최대 4개
```

응답은 프로젝트와 2D 설계안 4개임.

### `GET /api/projects`

최근 프로젝트 20개를 반환함.

### `GET /api/projects/{project_id}`

프로젝트, 2D 결과, 3D 자산, Design State, Validation을 반환함.

### `POST /api/projects/{project_id}/generate-3d`

```json
{
  "selected_2d_id": "CONCEPT-1",
  "output_goal": "auto",
  "quality_profile": "standard",
  "engine_override": null
}
```

응답의 `result_3d.assets`에는 조건에 따라 `fast`, `structural`, `high_quality`가 포함됨.

### `POST /api/projects/{project_id}/review-grade`

```json
{
  "requested_grade": "engineer_reviewed",
  "reviewer": "박명호",
  "note": "주요 치수와 구성 검토 완료"
}
```

`manufacturing_approved`는 제조 승인 프로세스 이후에만 사용해야 함.

## 회의

- `POST /api/meetings` 회의 프로젝트를 생성함
- `POST /api/projects/{id}/meeting/chunks` 음성 Chunk를 업로드함
- `POST /api/projects/{id}/meeting/analyze` Transcript를 분석함
- `POST /api/projects/{id}/meeting/generate-2d` 회의 내용으로 2D를 생성함
- `POST /api/projects/{id}/meeting/patch` 후속 회의 변경을 Revision으로 적용함

## Knowledge

- `POST /api/knowledge/ingest` 텍스트·Chunk를 인제스트함
- `POST /api/knowledge/ingest-file` 파일을 추출·인제스트함
- `POST /api/knowledge/search` Qdrant 검색을 수행함

## Worker 내부 API

- `POST /v1/generate/2d`
- `POST /v1/generate/3d`
- `POST /v1/meeting/transcribe`
- `POST /v1/meeting/analyze`
- `POST /v1/meeting/patch`
