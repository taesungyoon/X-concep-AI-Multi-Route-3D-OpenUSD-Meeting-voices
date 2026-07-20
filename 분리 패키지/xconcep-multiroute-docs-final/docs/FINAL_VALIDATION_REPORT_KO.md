# X concep AI NVIDIA 기술스택 최종 검증 보고서

검증 기준일: 2026-07-18

## 1. 검증 대상

- XconcepAI NVIDIA 기술스택 고도화전략 2026-07-02 자료 11쪽임
- X concep AI 소개서 2026-07-02 자료 23쪽임
- 기존 회의·Omniverse 풀스택 전달본임
- 사용자 제시 목표 아키텍처임

## 2. 자료 기반 핵심 확인

### 기술스택 전략 자료

자료는 기존 PHP·DRF·MySQL을 전면 교체하지 않고 NeMo Agent Toolkit, NIM, Qdrant, OpenUSD·Omniverse를 단계적으로 추가하는 방향을 제시함. 3D는 기존 GLB Viewer를 유지하면서 USD 후처리와 Omniverse 검수로 병행하고, Isaac Sim과 Cosmos는 장기 과제에 배치함.

### 서비스 소개서

소개서는 X concep AI를 요구사항에서 2D·3D·Proposal·Six-View로 연결되는 Pre-CAD Workflow Agent로 정의함. 소개서의 현재 출력 설명에는 STL이 Mesh 기반이며 Parametric CAD·제조 Feature는 향후 확장이라고 명시함. 고객 미팅 현장에서 요구사항을 즉시 시각화·3D화하는 영업 사용 사례도 제시함.

## 3. 기존 제작본 판정

### 일치한 부분

- PHP 반응형 UI임
- Gemma 계열 LLM용 vLLM·Ray Adapter임
- GPT Image API 외부 호출 분리임
- Hunyuan3D 로컬 3D 생성임
- 회의 음성 Chunk 전사와 요구사항 분석임
- GLB·STL·PNG·OpenUSD 출력임
- Omniverse Kit·Nucleus·WebRTC 확장 골격임

### 불일치했던 부분

- DRF·MySQL 제어 계층이 없었음
- Qdrant 설계 메모리와 RAG가 없었음
- NeMo Agent Toolkit 실제 Plugin·Runtime Profile이 없었음
- NeMo Retriever 파일 추출 경계가 없었음
- NIM·TensorRT-LLM·Triton의 역할 구분이 불명확했음
- Cosmos가 실제 3D Simulation Engine처럼 표현될 위험이 있었음
- 현재 Mesh 출력이 제조 상세 CAD로 과대 표현될 위험이 있었음

## 4. 수정 완료 항목

1. DRF Control Plane과 MySQL Model을 추가함
2. Project·Asset·GenerationJob·MeetingSession·TranscriptSegment를 관계형 DB로 관리함
3. Redis·Celery 비동기 Profile을 추가함
4. Qdrant Knowledge Service와 Asset Indexing·RAG Search를 추가함
5. NeMo Retriever 26.5 선택 설치 Profile과 Custom Qdrant 저장 Adapter를 추가함
6. NeMo Agent Toolkit 1.8 Plugin Package, YAML Workflow, 선택 Runtime Profile을 추가함
7. Gemma 커스텀 체크포인트의 기본 Serving은 vLLM·Ray로 유지함
8. TensorRT-LLM·Triton·NIM을 단계별 Serving 구조로 재정의함
9. NeMo ASR Local·Speech NIM·Faster-Whisper 경로를 유지함
10. NeMo ClusteringDiarizer 선택 Profile과 RTTM Speaker Mapping을 추가함
11. 회의 Transcript에 Qdrant 검색 문맥을 결합해 Gemma가 확정·변경·미확정·안전 요구를 구조화함
12. Hunyuan3D 결과를 GLB·STL·OpenUSD Layer Package로 변환함
13. OpenUSD에 Meeting Metadata·Revision·PhysicsScene·Variant 준비 구조를 유지함
14. Isaac Sim·Cosmos·DeepStream·TAO·Metropolis를 선택 확장으로 분리함
15. 서버 절대경로, 내부 JSON, 원본 음성 노출을 차단함

## 5. 최종 판정

### PoC·사내개발·고객시연

승인 가능함.

### 실제 GPU 통합 테스트

조건부 승인임. 실제 Gemma 체크포인트, GPT Image Key, Hunyuan3D 가중치, NeMo Speech·Retriever, NVIDIA Kit Runtime이 필요함.

### 인터넷 공개 운영

현재 상태로는 승인 불가함. 사용자 인증, Tenant 분리, 비동기 GPU Queue, 사용량 제한, 회의 동의·파기 정책, 비밀정보 관리가 추가되어야 함.

## 6. 의도적 제외

- 모델 가중치와 API Key 재배포임
- STEP·B-Rep·GD&T·공차 검증임
- 실제 Nucleus 계정과 Live Session임
- 실제 Isaac Sim Robot Joint 자동 구성임
- Cosmos 모델 Serving임
- DeepStream 실카메라 RTSP 테스트임
- 결제·Credit·Enterprise SSO임

## 7. 최종 전달 시점 제한사항

- Omniverse Web Client의 실제 npm 의존성 설치·Production Bundle은 NVIDIA 패키지 접근 가능한 환경에서 재검증해야 함
- Docker Engine 기반 전체 Container Build는 배포 서버에서 재검증해야 함
- 실제 모델·GPU Runtime 검증 전에는 Mock 통합 성공을 실서비스 성능 승인으로 해석하지 않음
