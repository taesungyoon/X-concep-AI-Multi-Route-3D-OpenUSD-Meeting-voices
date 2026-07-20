# X concep AI Multi-Route 3D·회의 음성·OpenUSD 최종 설치·운영 매뉴얼

## 1. 문서 목적

본 전달본은 현재 운영 중인 GPT Image 기반 2D 생성과 Hunyuan3D 로컬 3D 흐름을 유지하면서 OpenSCAD 구조 생성, Blender 고품질 자산 처리, OpenUSD·NVIDIA Omniverse 연계를 추가한 최종 기준 풀스택임.

사용자는 생성 엔진을 반드시 이해하거나 선택할 필요가 없으며 원하는 결과 수준을 선택하면 내부 Router가 적합한 경로를 조합함.

```text
텍스트·이미지 또는 회의 음성
        ↓
Gemma 요구사항 분석 + Qdrant RAG
        ↓
GPT Image API로 2D 설계안 4개 생성
        ↓
사용자가 2D 설계안 선택
        ↓
자동 추천 또는 결과 목적 선택
        ├─ 빠른 3D: Hunyuan3D
        ├─ 구조 중심 3D: OpenSCAD
        ├─ 고품질 3D: Hunyuan3D/OpenSCAD → Blender
        └─ 동작·OpenUSD: Blender → OpenUSD → Omniverse
```

## 2. 최종 적용 범위

### 사용자 기능

- 텍스트 단독, 이미지 단독, 텍스트·이미지 혼합 입력을 지원함
- 설비·모듈·부품 생성 유형을 지원함
- 2D 설계안 4개를 비교하고 선택함
- 자동 추천, 빠른 3D, 구조 중심 3D, 고품질 3D, 동작·OpenUSD 결과를 지원함
- 생성된 빠른·구조·고품질 결과를 탭으로 전환함
- GLB·STL·SCAD·Geometry JSON·PNG·USDA·USDC를 조건부 다운로드함
- 회의 음성을 Chunk 단위로 전사하고 Gemma가 요구사항을 구조화함
- 생성 결과에 Concept·Structured·Validated·Engineer Reviewed·Manufacturing Approved 등급을 적용함
- 더 빠르게, 구조를 정확하게, 더 사실적으로, 동작·OpenUSD로 재생성하는 사용자 중심 버튼을 제공함

### 내부 기능

- 기존 PHP Web과 Django REST Framework 제어 계층을 유지함
- MySQL에 프로젝트·Job·Asset·회의·검증 상태를 저장함
- Redis·Celery 비동기 Profile을 제공함
- NeMo Agent Toolkit을 선택적 Agent Workflow 계층으로 사용함
- Gemma 사용자 보유 체크포인트를 vLLM·Ray OpenAI 호환 API로 연결함
- GPT Image API만 외부 생성 서비스로 사용함
- Hunyuan3D, OpenSCAD, Blender, 음성 분석, OpenUSD는 로컬 실행 경로를 제공함
- NeMo Retriever Adapter와 Qdrant RAG를 연결함
- OpenUSD Layer, Omniverse Kit, Asset Validator, Nucleus, WebRTC, PhysX 연계 골격을 제공함

## 3. 디렉터리 구조

```text
frontend-php/             PHP 반응형 UI와 DRF Proxy
control-plane-drf/        프로젝트·Job·Asset·회의·검증 Control Plane
agent-layer-nat/          NeMo Agent Toolkit Plugin·Gateway·Workflow
knowledge-service/        NeMo Retriever Adapter·Qdrant RAG
python-worker/            LLM·GPT Image·Hunyuan·OpenSCAD·Blender·ASR·OpenUSD
inference/                vLLM/Ray·TensorRT-LLM·Triton·NIM 설정
omniverse-kit/            Kit App·Asset Converter·Validator·Nucleus Script
omniverse-web-client/     Omniverse WebRTC Client 골격
simulation/               Isaac Sim·Cosmos 적용 경계
vision-layer/             Metropolis·DeepStream·TAO 확장 경계
scripts/                  로컬 실행·Smoke Test
storage/                  입력·회의·생성 결과 저장
```

## 4. 최소 요구 환경

### Mock 검증 환경

- PHP 8.2 이상을 권장함
- Python 3.11 또는 3.12를 권장함
- Node.js는 JavaScript 정적 검증 시 사용함
- Docker Engine과 Docker Compose Plugin을 권장함
- GPU 없이 Mock 전체 흐름을 실행할 수 있음

### 운영 환경

- Gemma 체크포인트를 구동할 NVIDIA GPU Cluster가 필요함
- Hunyuan3D용 별도 GPU Worker를 권장함
- Blender Headless 렌더링용 GPU Worker를 분리하는 것이 적절함
- Omniverse Kit RTX·WebRTC는 별도 GPU Session 운영을 권장함
- 공유 Storage 또는 Object Storage가 필요함
- MySQL·Redis·Qdrant 영속 Volume과 백업 정책이 필요함

## 5. Docker Mock 실행

```bash
cp .env.example .env
docker compose up --build
```

접속 주소임.

```text
사용자 UI      http://localhost:8080
상태 API       http://localhost:8080/api/system-status
DRF Health     http://localhost:8080/health
```

Mock 모드에서는 외부 API·실제 GPU 없이 다음 흐름을 검증함.

```text
PHP → DRF → Agent Gateway → Python Worker
              └→ Knowledge Service → Qdrant
Mock 2D 4안 → Hunyuan Mock + OpenSCAD Fallback + Blender Fallback
→ GLB·STL·PNG·SCAD·USDA·USDC
```

## 6. Docker 없이 로컬 실행

Linux 또는 macOS임.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r python-worker/requirements.txt
pip install -r control-plane-drf/requirements.txt
pip install -r agent-layer-nat/requirements.txt
pip install -r knowledge-service/requirements.txt
VENV_BIN="$PWD/.venv/bin" ./scripts/run-local.sh
```

Windows는 `scripts/run-local.ps1`이 서비스별 실행 명령을 출력함.

## 7. 운영 환경변수

```env
PIPELINE_MODE=production

LLM_MODE=vllm
VLLM_BASE_URL=http://RAY_HEAD:8000/v1
VLLM_API_KEY=local-not-required
GEMMA_MODEL_NAME=gemma-4-64b-local

OPENAI_IMAGE_MODE=openai
OPENAI_API_KEY=sk-...
OPENAI_IMAGE_MODEL=gpt-image-2

HUNYUAN_MODE=local_api
HUNYUAN_API_URL=http://HUNYUAN3D:8081

OPENSCAD_MODE=native
OPENSCAD_BIN=openscad
OPENSCAD_TIMEOUT_SECONDS=600

BLENDER_MODE=native
BLENDER_BIN=blender
BLENDER_TIMEOUT_SECONDS=1800

SPEECH_MODE=nemo_asr
NEMO_ASR_MODEL=nvidia/parakeet-tdt-0.6b-v3
DIARIZATION_MODE=none

OPENUSD_GENERATE_USDC=true
OMNIVERSE_ENABLED=true
OMNIVERSE_GENERATE_LAYERS=true
OMNIVERSE_ENABLE_PHYSICS=true
OMNIVERSE_ENABLE_VARIANTS=true
OMNIVERSE_NUCLEUS_URL=omniverse://NUCLEUS/Projects/Xconcep
OMNIVERSE_STREAM_URL=https://KIT-WEBRTC-ENDPOINT
```

`Gemma 4 64B`는 사용자 보유 커스텀·병합 체크포인트의 Served Model Name으로 취급함. 실제 모델 구조, Tokenizer, Chat Template, 멀티모달 Processor 및 vLLM 호환성을 운영 서버에서 검증해야 함.

## 8. 사용자 생성 흐름

### 8.1 직접 입력

1. 프롬프트를 입력함
2. 참고 이미지를 최대 4장 업로드함
3. 설비·모듈·부품 유형을 선택함
4. 원하는 결과를 선택함
5. 2D 설계안 4개를 생성함
6. 한 개 설계안을 선택함
7. 3D 생성 결과를 확인함
8. 검증 등급과 사용 범위를 확인함
9. 필요한 파일을 내려받음

### 8.2 결과 목적과 내부 경로

| 사용자 선택 | 기본 실행 경로 | 목적 |
|---|---|---|
| 자동 추천 | 규칙 Router + Gemma 계획 | 적합한 복수 경로를 자동 조합함 |
| 빠른 3D | Hunyuan3D | 이미지 기반 외형을 빠르게 확인함 |
| 구조 중심 3D | Geometry JSON → OpenSCAD | 치수·프레임·기계 구조를 우선함 |
| 고품질 3D | Hunyuan/OpenSCAD → Blender | 조립·재질·조명·렌더링을 적용함 |
| 동작·OpenUSD | Blender → OpenUSD → Omniverse | 협업·Revision·물리·동작 자산을 준비함 |

고급 설정에서 엔진 직접 선택이 가능하지만 기본 사용자는 기술 엔진을 선택하지 않아도 됨.

## 9. Design State와 결과 일관성

모든 엔진이 동일한 Design State를 참조함.

```json
{
  "design_id": "DESIGN-10059",
  "revision": 3,
  "selected_2d_id": "CONCEPT-B",
  "units": "mm",
  "coordinate_system": "Z_UP_RIGHT_HANDED",
  "purpose": "산업용 비전 검사 모듈",
  "dimensions": {"width_mm": 900, "depth_mm": 600, "height_mm": null},
  "components": ["frame", "camera", "conveyor", "safety_cover"],
  "visual": {"main_color": "blue", "material_direction": "aluminum and polycarbonate"}
}
```

필수 일치 우선순위임.

```text
기능 및 동작 원리
> 필수 구성요소
> 주요 치수와 배치
> 전체 비례와 실루엣
> 재질·곡면·세부 외관
```

GPT Image·Hunyuan3D·OpenSCAD·Blender 결과를 메시 단위로 동일하게 만드는 것이 아니라 동일한 설계 의도와 기능 구조를 다른 표현 방식으로 제공함.

## 10. 자동 라우팅과 Fallback

### 10.1 결정 규칙

- 치수·홀·프레임·브래킷이 존재하면 OpenSCAD 후보로 분류함
- 이미지 중심·곡면·손잡이·외장 커버가 핵심이면 Hunyuan3D 후보로 분류함
- 재질·조명·애니메이션·OpenUSD가 필요하면 Blender 후처리를 추가함
- 표준 모터·센서·실린더·베어링은 향후 Catalog Asset 우선 정책을 적용함

### 10.2 신뢰도 처리

- 높은 신뢰도에서는 주 경로를 실행함
- 중간 신뢰도에서는 주 경로와 저비용 Preview를 함께 준비함
- 낮은 신뢰도에서는 빠른 Mesh와 구조 Blockout을 병렬 생성함

### 10.3 자동 Fallback

```text
Hunyuan3D 실패 → 입력 전처리·재시도 → 구조 모델 제공
OpenSCAD 실패 → 문제 Feature 억제 → 단순 구조 → Blender 보완
Blender 실패 → 상위 GLB·STL 제공 → 고품질 작업만 재Queue
OpenUSD 실패 → GLB 유지 → Omniverse Asset Converter 재변환
```

Job은 즉시 실패 종료하지 않고 Fallback Processing으로 전환함.

## 11. OpenSCAD

OpenSCAD는 결정론적 구조 생성 경로임.

지원 범위임.

- 프레임·베이스·플레이트·브래킷임
- 박스·실린더·축·롤러임
- 홀·슬롯·단순 반복 구조임
- SCAD·STL·3MF 확장 기반임

현재 Worker는 `geometry.json`, `model.scad`, `model_structural.stl`, `model_structural.glb`, `assembly_manifest.json`을 생성함.

Native OpenSCAD가 없으면 Trimesh 기반 Fallback 구조 모델을 생성하여 전체 UI 흐름을 유지함.

## 12. Hunyuan3D

Hunyuan3D는 기존 운영 방향을 유지하는 선택 경로임.

주요 활용 범위임.

- 빠른 이미지 기반 Mesh임
- 제품 외형·곡면·손잡이·커버임
- GLB 기반 웹 3D 검토임
- Blender 후처리 기초 Mesh임

Worker는 Binary GLB, Base64 JSON, URL 및 공유 경로 응답을 처리함. 상업 서비스 적용 전 사용 중인 Hunyuan3D 버전과 License 조건을 별도 검토해야 함.

## 13. Blender

Blender는 독립 생성 선택지이자 공통 자산 처리 Hub임.

- Hunyuan3D와 OpenSCAD 결과를 Import함
- 단위·좌표·원점을 통일함
- Normal·Mesh를 정리함
- 산업용 Material Preset을 적용함
- Camera·Lighting을 자동 배치함
- Preview·Standard·Final Profile을 적용함
- GLB·PNG·USD·BLEND를 조건부 출력함

모든 Job에 Final Profile을 적용하지 않고 고품질·OpenUSD 요청에만 고비용 처리를 실행함.

## 14. OpenUSD·Omniverse

권장 Layer 구조임.

```text
root.usda
├─ geometry.usda 또는 Blender render_asset.usdc
├─ looks.usda
├─ meeting.usda
└─ revisions/rev_XXX.usda
```

Blender Native USD가 존재하면 이를 Render Asset으로 참조함. Native USD가 없으면 직접 Mesh USD를 생성하는 Fallback을 사용함. 실제 Omniverse 운영에서는 GLB → Asset Converter → USD 경로도 대체 경로로 사용함.

Omniverse 확장 범위임.

- Kit Review App임
- Asset Validator임
- Nucleus Publish임
- WebRTC RTX Stream임
- PhysX Collision·Joint 준비임
- Variant와 Revision 검토임

OpenUSD는 STEP·B-Rep·CAD Feature Tree를 대체하지 않음.

## 15. 회의 음성 분석

### 흐름

```text
브라우저 MediaRecorder
→ 15초 Chunk
→ DRF Meeting Session
→ NeMo ASR / Speech NIM / Faster-Whisper
→ 선택적 NeMo Diarization
→ Qdrant 문맥 검색
→ Gemma 요구사항 구조화
→ 2D 4안 → 3D Route
```

구조화 항목임.

- 회의 요약임
- 확정 요구사항임
- 변경사항임
- 치수임
- 구성품임
- 동작 원리임
- 안전 요구사항임
- 미확정 항목임
- Action Item임
- 생성 프롬프트임

화자 근거가 없는 Provider에서는 Speaker를 임의 지정하지 않음. 실제 Diarization 결과가 존재할 때만 화자를 기록함.

## 16. 검증 등급과 활용 범위

| 등급 | 의미 | 활용 범위 |
|---|---|---|
| Concept | 시각 결과 또는 초기 Mesh가 생성됨 | 외관·아이디어 검토임 |
| Structured | 구성과 주요 치수가 반영됨 | 구조·배치 검토임 |
| Validated | 자동 품질 검사를 통과함 | 후속 설계 입력임 |
| Engineer Reviewed | 엔지니어 검토 기록이 존재함 | 상세설계 진행임 |
| Manufacturing Approved | 제조 승인 담당자가 승인함 | 제작 기준 데이터 후보임 |

자동 Worker는 최대 Validated 등급까지만 부여함. Engineer Reviewed와 Manufacturing Approved는 DRF 검토 API로 검토자와 기록을 저장해야 함.

제조 활용 기준임.

> 생성 결과는 생성 방식과 검증 수준에 따라 컨셉 검토, 구조 검토, 상세설계 입력 및 시뮬레이션 자산으로 구분하여 활용함. 주요 치수, 조립 조건, 공차 및 제조 조건에 대한 엔지니어 검증을 완료한 결과는 후속 CAD 설계와 제작 검토의 입력 데이터로 활용함.

최종 제조 승인 절차임.

```text
AI 생성 → 자동 검증 → 엔지니어 검토 → 상세 CAD 보완 → 제조성 검토 → 최종 승인
```

## 17. 비동기 Queue와 Worker 분리

권장 Worker Queue임.

```text
CPU Queue       OpenSCAD·검증·변환
GPU 3D Queue    Hunyuan3D
GPU Render      Blender
RTX Session     Omniverse Kit·WebRTC
Speech Queue    ASR·Diarization
```

동일한 GPU에서 Hunyuan3D와 Blender Final Render를 동시에 실행하지 않는 것이 적절함.

운영 Async Profile임.

```bash
docker compose --profile async up -d celery-worker
```

실서비스에서는 Job Progress, Retry, Timeout, 사용자별 동시 처리 제한 및 GPU Resource Lock을 추가함.

## 18. 캐시와 부분 재생성

캐시 키 권장 항목임.

```text
Design Revision
+ Engine
+ Engine Version
+ Material Preset
+ Quality Profile
+ Output Format
```

부분 재생성 예시임.

- 프레임 폭 변경 시 OpenSCAD 구조만 재생성함
- 손잡이 색상 변경 시 Blender Material만 갱신함
- 외장 커버 형상 변경 시 Hunyuan3D Mesh만 재생성함
- OpenUSD 추가 요청 시 Blender Export와 USD Packaging만 실행함

## 19. RAG와 Knowledge Service

- NeMo Retriever를 문서 추출·Chunk 정규화 계층으로 선택 적용함
- Qdrant를 기존 Vector Store로 유지함
- 프로젝트, 2D 설계, 3D 결과, 회의 내용과 문서 Chunk를 검색함
- 회사별 Collection 또는 Payload Filter로 Tenant를 분리해야 함

기본 Mock는 In-memory Qdrant Client와 Hash Embedding을 사용함. 운영에서는 Qdrant Server와 Embedding NIM 또는 검증된 Local Embedding Model을 사용함.

## 20. 보안 기준

- 사용자 인증과 회사별 Tenant 권한을 추가해야 함
- 업로드 확장자와 MIME를 모두 검사함
- 원본 업로드·회의 음성·내부 Analysis JSON을 정적 URL로 노출하지 않음
- Path Traversal과 Storage Root 외부 경로를 차단함
- OpenAI Image API로 전달되는 데이터 범위를 명시함
- 회의 녹음 동의, 보존기간 및 파기 정책을 수립함
- Nucleus·WebRTC는 사내 인증과 TLS를 적용함
- API Key를 Repository에 저장하지 않음

## 21. Smoke Test

서비스 실행 후 다음 명령을 실행함.

```bash
./scripts/smoke-test.sh
```

검증 항목임.

- Web·DRF·Agent·Worker·Knowledge 상태임
- 2D 4안 생성임
- 자동 Multi-Route 3D 생성임
- fast·structural·high_quality 자산 생성임
- 검증 등급과 OpenUSD URL 생성임

## 22. 운영 배포 전 체크리스트

- 실제 Gemma 체크포인트 vLLM·Ray TP/PP·NCCL 검증함
- GPT Image 비용·Rate Limit·Retry를 검증함
- Hunyuan3D 생성시간·VRAM·동시 처리량을 검증함
- OpenSCAD 복잡 Boolean Timeout을 검증함
- Blender Preview·Final 처리시간과 GPU 메모리를 검증함
- ASR 한국어 소음 환경과 화자 분리 정확도를 검증함
- OpenUSD Texture·Material Binding을 검증함
- Omniverse Kit·Nucleus·WebRTC 실기동을 검증함
- 인증·Tenant·Queue·Quota·감사 로그를 추가함
- 백업·복구·보존·파기 정책을 확정함

## 23. 공식 참고 문서

- NVIDIA NeMo Agent Toolkit: https://docs.nvidia.com/nemo/agent-toolkit/latest/index.html
- vLLM Multi-Node Serving: https://docs.vllm.ai/en/latest/examples/ray_serving/multi-node-serving/
- OpenSCAD Documentation: https://openscad.org/documentation
- Blender USD Manual: https://docs.blender.org/manual/en/latest/files/import_export/usd.html
- Omniverse Asset Converter: https://docs.omniverse.nvidia.com/extensions/latest/ext_asset-converter.html
- OpenUSD: https://openusd.org/
