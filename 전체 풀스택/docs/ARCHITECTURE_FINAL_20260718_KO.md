# X concep AI NVIDIA 통합 아키텍처 최종본

## 1. 최종 운영 구조

```text
사용자 브라우저 / 모바일
  ├─ 직접 프롬프트 + 참고 이미지
  └─ 회의 음성 15초 Chunk + Transcript 수정
          │
          ▼
PHP Web UI / Reverse Proxy
          │
          ▼
Django REST Framework Control Plane
  ├─ MySQL: Project / Job / Asset / Meeting / Transcript / Revision
  ├─ Redis + Celery: 비동기 Job 선택 프로파일
  ├─ Qdrant: 과거 프롬프트 / 회의 / 2D·3D 자산 검색
  └─ 인증·Tenant·결제 확장 경계
          │
          ▼
Agent Boundary
  ├─ Deterministic REST Gateway: 생성 Job의 고정 실행 경로
  └─ NVIDIA NeMo Agent Toolkit Profile
      ├─ Tool Calling / ReAct Workflow
      ├─ 평가·프로파일링·Observability 확장
      └─ X concep 제조 Tool Plugin
          │
          ├──────── Knowledge Service
          │           ├─ NeMo Retriever Library: 문서·이미지·오디오 추출 선택 프로파일
          │           ├─ NVIDIA Embedding NIM 선택
          │           └─ Custom Qdrant Adapter / RAG
          │
          └──────── Python AI Worker
                      ├─ 회의 STT: NeMo ASR Local / Speech NIM / Faster-Whisper
                      ├─ 화자 분리: NeMo ClusteringDiarizer 선택 프로파일
                      ├─ LLM: Gemma 계열 사용자 체크포인트
                      │   └─ vLLM + Ray 기본 분산 서빙
                      ├─ 2D: GPT Image API만 외부 호출
                      ├─ 3D: Hunyuan3D Local
                      └─ OpenUSD Layer / GLB / STL / PNG
                                  │
                                  ▼
3D·Physical AI
  ├─ Three.js: 일반 웹 GLB Viewer
  ├─ OpenUSD: root / geometry / looks / meeting / revision Layer
  ├─ Omniverse Kit: RTX / Asset Validator / Nucleus / WebRTC
  ├─ Isaac Sim: Joint·Collision·Robot·Sensor 물리 검증 선택
  └─ Cosmos: 멀티뷰·비디오·월드 시나리오가 필요한 과제에 한정

Factory Vision 선택 프로파일
  Camera/RTSP → DeepStream → TAO Model → Metropolis Event → DRF / Qdrant / OpenUSD Metadata
```

## 2. 계층별 경계

### PHP / DRF

PHP는 사용자 화면과 Reverse Proxy만 담당함. DRF는 프로젝트·Job·회의 상태의 단일 제어 계층임. 생성 Worker가 MySQL을 직접 수정하지 않도록 분리함.

### NeMo Agent Toolkit

NeMo Agent Toolkit은 DRF를 대체하지 않음. 사용자 의도에 따라 검색·분석·생성·검증 Tool을 선택하는 Agent Workflow, 평가와 Trace에 적용함. 거래 상태와 재시도 정책은 DRF·Celery가 소유함.

### NIM / TensorRT-LLM / Triton

세 기술을 병렬 대안으로 표현하지 않음.

- TensorRT-LLM: 지원 LLM을 NVIDIA GPU에서 최적화하는 Runtime·Engine 계층임
- Triton: 모델 Repository, 스케줄링, 동적 배칭, HTTP/gRPC Serving 계층임
- NIM: 모델별 표준 API와 운영 패키징을 제공하는 Microservice 계층임

사용자 보유 Gemma 커스텀 체크포인트는 vLLM·Ray를 1차 경로로 유지함. TensorRT-LLM은 모델 지원, 양자화 정확도, 처리량을 검증한 뒤 전환함.

### NeMo Retriever / Qdrant

NeMo Retriever Library는 파일 추출·구조화·Embedding 파이프라인임. 현재 NVIDIA가 기본 검증하는 Vector DB 경로는 LanceDB이므로 Qdrant 연결은 X concep의 Custom Adapter로 관리함. 이 전달본은 추출 결과를 안정된 Chunk 계약으로 정규화한 뒤 Qdrant에 저장함.

### OpenUSD / Omniverse / Isaac Sim / Cosmos

- OpenUSD는 3D 자산의 Layer·Variant·Metadata 구조임
- Omniverse는 자산 검수·협업·RTX Streaming Application 계층임
- Isaac Sim은 실제 물리·Robot·Sensor Simulation 계층임
- Cosmos는 일반 CAD 변환 엔진이 아니며 Physical AI용 World·Video Scenario가 필요한 경우에만 적용함

### Metropolis / DeepStream / TAO

사용자 입력 기반 2D·3D 생성의 필수 계층이 아님. 공장 카메라, 현장 이벤트, 비전 검사, Digital Twin 상태 동기화 요구가 있을 때 별도 프로파일로 활성화함.

## 3. 제품 결과 범위

현재 주 출력은 Hunyuan3D 기반 Mesh임.

- 제공 가능: 2D 컨셉, GLB, STL, PNG, USDA, USDC, 회의 Metadata, Revision Layer
- 제공 불가: STEP B-Rep, 완전한 CAD Feature Tree, GD&T, 공차 누적, 자동 제조 승인

따라서 제품 문구는 `제조 요구사항을 반영한 Pre-CAD 컨셉 및 후속 CAD 연계 자산`으로 사용함.
