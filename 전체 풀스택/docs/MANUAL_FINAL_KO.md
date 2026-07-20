# X concep AI NVIDIA 통합 풀스택 설치·운영 매뉴얼

## 1. 제공 기능

- 프롬프트·참고 이미지 혼합 입력함
- 회의 음성을 15초 Chunk로 업로드하고 실시간에 가까운 Transcript를 누적함
- NeMo ASR Local, NVIDIA Speech NIM, Faster-Whisper 중 하나를 선택함
- 선택 시 NeMo ClusteringDiarizer로 화자 Label을 적용함
- 회의 내용과 Qdrant 과거 설계 문맥을 Gemma가 분석함
- 확정 요구, 변경, 치수, 구성품, 안전, 미확정, Action Item을 구조화함
- GPT Image API로 2D 설계안 4개를 생성함
- 선택한 2D로 Hunyuan3D 로컬 3D를 생성함
- GLB·STL·PNG·USDA·USDC를 제공함
- Omniverse Kit·Asset Validator·Nucleus·WebRTC·PhysX 확장 경계를 제공함

## 2. 디렉터리

```text
frontend-php/           PHP UI와 DRF Proxy
control-plane-drf/      Project·Job·Meeting Control Plane
agent-layer-nat/        NeMo Agent Toolkit Plugin·Gateway·Workflow
knowledge-service/      NeMo Retriever Adapter·Qdrant RAG
python-worker/          LLM·Image·3D·ASR·OpenUSD Worker
inference/              vLLM/Ray·TensorRT-LLM·Triton·NIM 가이드
omniverse-kit/          Kit App·Validator·Nucleus Script
simulation/             Isaac Sim·Cosmos 적용 경계
vision-layer/           Metropolis·DeepStream·TAO 확장
storage/                업로드·회의·생성 결과
```

## 3. 기본 Mock 실행

```bash
cp .env.example .env
docker compose up --build
```

접속 주소임.

```text
http://localhost:8080
```

Mock 모드는 외부 API와 GPU 없이 아래 통합 흐름을 확인함.

```text
PHP → DRF → Agent Gateway → Python Worker
                  └→ Qdrant Knowledge Service
2D Mock → 3D Mock → OpenUSD → Three.js Viewer
```

## 4. 실제 운영 설정

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

SPEECH_MODE=nemo_asr
INSTALL_NEMO_SPEECH=true
NEMO_ASR_MODEL=nvidia/parakeet-tdt-0.6b-v3

EMBED_MODE=nim
EMBED_URL=http://EMBEDDING_NIM:8000
QDRANT_COLLECTION=xconcep_memory
```

## 5. MySQL·Qdrant·Redis

기본 Docker Compose가 MySQL 8.4, Qdrant 1.18.2, Redis를 실행함.

```env
MYSQL_DATABASE=xconcep
MYSQL_USER=xconcep
MYSQL_PASSWORD=strong-password
MYSQL_ROOT_PASSWORD=strong-root-password
```

운영 시 Docker Volume을 정기 백업하고 Qdrant Snapshot 정책을 설정함.

## 6. NeMo Agent Toolkit

기본 생성 API는 재시도와 상태 통제를 위해 결정론적 Gateway를 사용함. Agentic Tool 선택, 평가, Trace가 필요하면 NAT Profile을 활성화함.

```env
INSTALL_NAT=true
AGENT_RUNTIME=nat
```

```bash
docker compose --profile nat up --build
```

NAT Runtime은 `nat serve`로 실행되며 X concep Tool Plugin을 로드함. Gateway의 `/v1/workflows/agent-run`이 NAT `/v1/workflow`로 전달함.

## 7. NeMo Retriever + Qdrant

기본은 텍스트·PDF fallback 추출과 Qdrant 저장임.

```env
NEMO_RETRIEVER_MODE=fallback
INSTALL_NEMO_RETRIEVER=false
```

NeMo Retriever Library를 사용하려면 아래처럼 설정함.

```env
NEMO_RETRIEVER_MODE=nemo
INSTALL_NEMO_RETRIEVER=true
```

```bash
docker compose build knowledge-service
docker compose up -d knowledge-service
```

파일 인제스트 API임.

```bash
curl -F 'file=@document.pdf' \
     -F 'project_id=PRJ-001' \
     -F 'metadata_json={"domain":"automation"}' \
     http://localhost:8080/api/knowledge/ingest-file
```

NeMo Retriever의 기본 검증 VDB가 Qdrant는 아니므로 본 시스템은 추출 Chunk를 정규화한 뒤 자체 Embedding·Qdrant Adapter로 저장함.

## 8. 회의 음성 분석

### 기본 흐름

1. `회의 음성 분석`을 선택함
2. 브라우저에서 녹음을 시작함
3. MediaRecorder가 15초 단위 Chunk를 보냄
4. DRF가 음성 파일과 Transcript Segment를 저장함
5. Qdrant에서 유사 프로젝트·설계 문맥을 검색함
6. Gemma가 회의 요구사항을 JSON으로 구조화함
7. 사용자가 Transcript와 미확정 항목을 확인함
8. `현재 내용으로 2D 생성`을 실행함
9. 후속 발언은 Revision Patch로 저장함

### Speech Provider

```env
SPEECH_MODE=nemo_asr       # NVIDIA NeMo local
SPEECH_MODE=nvidia_nim     # 사내 Speech NIM
SPEECH_MODE=faster_whisper # 대체 경로
SPEECH_MODE=mock           # UI 검증
```

### 화자 분리

기본값은 화자를 추정하지 않음.

```env
DIARIZATION_MODE=none
```

NeMo Offline Diarization을 사용할 때만 활성화함.

```env
DIARIZATION_MODE=nemo
NEMO_DIARIZER_CONFIG=/models/diarizer-config.yaml
```

실제 Streaming Speaker Diarization은 Speech NIM WebSocket/gRPC 운영 Profile에서 별도 부하·정확도 검증함.

## 9. vLLM·Ray

```bash
export GEMMA_MODEL_PATH=/models/gemma-custom-64b
export GEMMA_SERVED_MODEL_NAME=gemma-4-64b-local
export VLLM_TP_SIZE=4
export VLLM_PP_SIZE=2
./inference/vllm-ray/serve-gemma.sh
```

확인함.

```bash
curl http://RAY_HEAD:8000/v1/models
```

사용자 보유 체크포인트가 vLLM 멀티모달 Processor를 지원하지 않으면 Gemma를 텍스트 요구사항 분석 전용으로 사용하고 이미지 분석 Model을 별도 분리함.

## 10. TensorRT-LLM·Triton·NIM

- TensorRT-LLM은 Gemma 지원과 양자화 정확도가 확인될 때 적용함
- Triton은 LLM·Embedding·ASR·Vision Model을 통합 Serving하고 동적 배칭이 필요할 때 적용함
- NIM은 지원 Model의 표준 API·운영 패키지가 필요할 때 적용함

현재 vLLM/Ray 경로를 먼저 안정화한 뒤 동일 Prompt Set으로 처리량·TTFT·정확도 Benchmark를 수행함.

## 11. Hunyuan3D

```env
HUNYUAN_MODE=local_api
HUNYUAN_API_URL=http://HUNYUAN3D:8081
```

Worker는 Binary GLB, JSON Base64, URL, 공유 경로 응답을 처리함. 운영 전 Hunyuan3D License와 상업 배포 조건을 검토함.

## 12. OpenUSD·Omniverse

기본 결과임.

```text
result/
├─ model.glb
├─ model.stl
├─ render.png
├─ model.usda
├─ model.usdc
└─ openusd/
   ├─ root.usda
   ├─ geometry.usda
   ├─ looks.usda
   ├─ meeting.usda
   ├─ revisions/
   └─ manifest.json
```

Omniverse Profile임.

```bash
docker compose -f docker-compose.yml -f docker-compose.omniverse.yml up -d
```

실제 Kit Runtime, Nucleus 인증, WebRTC TURN/STUN은 운영 환경에서 확인함.

## 13. Isaac Sim·Cosmos·공장 비전

- Isaac Sim: Joint, Collision, Robot, Sensor가 정의된 USD 자산을 검증할 때 사용함
- Cosmos: 멀티뷰·Video·World Scenario 생성 과제에만 사용함
- DeepStream·TAO·Metropolis: RTSP Camera와 현장 Event를 3D 자산 Metadata에 연결할 때 사용함

해당 기술은 현재 핵심 Prompt-to-3D 경로를 차단하지 않는 선택 Profile임.

## 14. 운영 보안

- OpenAI Key를 PHP·Browser에 노출하지 않음
- 외부 전송은 GPT Image 생성에 필요한 Prompt와 Reference Image로 제한함
- 원본 회의 음성·내부 JSON은 정적 Web 경로에서 차단함
- 내부 vLLM, Qdrant, MySQL, Hunyuan3D, NIM Port를 인터넷에 공개하지 않음
- User·Company Tenant별 Storage와 DB Query Filter를 추가함
- 회의 녹음 동의, 보존기간, 자동 파기 정책을 적용함
- Download URL은 인증·만료형 URL로 전환함

## 15. 운영 배포 전 필수 항목

1. Enterprise 인증·Tenant 분리함
2. `SYNC_PIPELINE=false`와 Celery GPU Queue를 적용함
3. Model별 GPU Queue·Concurrency·Timeout을 설정함
4. 실제 Gemma Checkpoint의 vLLM·Ray 분산을 검증함
5. GPT Image 실제 호출 비용과 Retry를 검증함
6. Hunyuan3D VRAM·생성시간·동시성을 검증함
7. NeMo ASR 한국어 정확도와 회의 환경 Noise를 평가함
8. Qdrant Backup·Snapshot·Retention을 적용함
9. OpenUSD Asset Validator와 Nucleus 권한을 검증함
10. 개인정보·기밀 설계 데이터 처리 정책을 승인함
