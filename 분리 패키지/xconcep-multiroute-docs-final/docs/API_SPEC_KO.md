# API 명세

## PHP Gateway

### 상태

```http
GET /health
GET /api/system-status
GET /api/projects
```

### 직접 입력 프로젝트

```http
POST /api/projects
POST /api/projects/{project_id}/generate-2d
POST /api/projects/{project_id}/select-2d
POST /api/projects/{project_id}/generate-3d
GET  /api/projects/{project_id}
```

### 회의 프로젝트

#### 회의 생성

```http
POST /api/meetings
Content-Type: application/json

{"category":"equipment"}
```

#### 오디오 Chunk 업로드

```http
POST /api/projects/{project_id}/meeting/chunks
Content-Type: multipart/form-data

audio=<webm/wav>
chunk_index=0
```

#### 회의 분석

```http
POST /api/projects/{project_id}/meeting/analyze
Content-Type: application/json

{"transcript":"선택적으로 수동 보정한 전체 회의문"}
```

#### 회의 기준 2D 생성

```http
POST /api/projects/{project_id}/meeting/generate-2d
```

#### 회의 변경 Patch

```http
POST /api/projects/{project_id}/meeting/patch
Content-Type: application/json

{"transcript":"변경사항을 포함한 최신 회의문"}
```

## Python Worker

### 상태

```http
GET /health
```

### 2D 생성

```http
POST /v1/generate/2d
```

### 3D·OpenUSD 생성

```http
POST /v1/generate/3d
```

요청 예시임.

```json
{
  "project_id": "PRJ-001",
  "prompt": "단일 FPCB 벤딩 유닛",
  "category": "equipment",
  "selected_2d_id": "CONCEPT-003",
  "selected_image_path": "projects/PRJ-001/2d/concept-003.png",
  "meeting_analysis": {},
  "revision": 4
}
```

### 회의 전사

```http
POST /v1/meeting/transcribe
```

```json
{
  "project_id": "PRJ-001",
  "audio_path": "projects/PRJ-001/meeting/audio/chunk-000.webm",
  "chunk_index": 0,
  "language": "ko"
}
```

### 회의 분석

```http
POST /v1/meeting/analyze
```

### 회의 Patch

```http
POST /v1/meeting/patch
```

## 산출물 URL

```text
/storage/projects/{project_id}/result/model.glb
/storage/projects/{project_id}/result/model.stl
/storage/projects/{project_id}/result/render.png
/storage/projects/{project_id}/result/model.usda
/storage/projects/{project_id}/result/model.usdc
/storage/projects/{project_id}/result/openusd/root.usda
/storage/projects/{project_id}/result/openusd/manifest.json
```
