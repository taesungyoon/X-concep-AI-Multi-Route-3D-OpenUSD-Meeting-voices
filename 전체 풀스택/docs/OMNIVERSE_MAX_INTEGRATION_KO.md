# NVIDIA Omniverse 최대 활용 방안 및 구현 내용

## 1. 적용한 기술

### OpenUSD Layer Composition

3D 결과를 단일 USD 파일로만 저장하지 않고 Geometry·Looks·Meeting·Revision Layer로 분리함. 회의 분석과 설계 변경 이력을 장면 형상과 분리하여 관리함.

### Kit SDK App

`omniverse-kit/apps/xconcep.meeting_review.kit`에 전용 앱 설정을 포함함. RTX Renderer, Viewport, USD Context, PhysX, Asset Converter, Asset Validator, Nucleus Client, Livestream Extension을 의존성으로 선언함.

### Custom Kit Extension

`xconcep.meeting.review` 확장에서 다음을 제공함.

- Manifest 경로 입력
- Root Stage 열기
- 자동 Reload
- Revision·Design Variant 선택
- Asset Validator 실행
- Nucleus 게시 대상 표시

### PhysX / UsdPhysics

OpenUSD Root Stage에 PhysicsScene을 정의하고 Mesh Prim에 Collision API 적용 준비 데이터를 기록함. Hunyuan3D Mesh의 실제 충돌 정확도는 별도 Convex Decomposition 또는 Simplified Collider 생성이 필요함.

### Asset Converter

Kit Python에서 GLB·FBX·OBJ를 USD로 변환하는 스크립트를 포함함.

```bash
kit --exec omniverse-kit/scripts/convert_glb_to_usd.py --source model.glb --target model.usdc
```

### Asset Validator

Kit Runtime에서 OpenUSD Stage를 검증하는 스크립트를 포함함.

```bash
kit --exec omniverse-kit/scripts/validate_asset.py --asset model.usda --json validation.json
```

### Nucleus 게시

Layer Package를 `omniverse://` 경로로 복사하는 `publish_nucleus.py`를 포함함. 실제 접속은 Enterprise Nucleus 계정·권한·TLS 설정이 필요함.

### Live Collaboration

Nucleus에 게시된 Root Stage를 기반으로 Live Session을 구성할 수 있도록 Layer 구조를 분리함. 회의 진행자만 편집하고 참여자는 Viewer로 접속하는 운영을 1차 권장함.

### WebRTC Streaming

Kit App에 `omni.kit.livestream.app`과 WebRTC Stream Type을 설정함. PHP 결과 화면은 `OMNIVERSE_STREAM_URL`이 설정되면 RTX 검토 버튼을 노출함.

### Omniverse Web SDK

`omniverse-web-client/`에 `@nvidia/ov-web-rtc`를 사용하는 별도 브라우저 연결 예제를 포함함. 실제 인증·세션 할당 방식은 Kit App Streaming 배포 환경에 맞춰 조정해야 함.

## 2. 권장 운영 토폴로지

```text
GPU Cluster A
- Ray Head / Worker
- vLLM Gemma

GPU Server B
- Hunyuan3D API

GPU Server C
- Omniverse Kit RTX App
- WebRTC Encoder

Infrastructure
- PHP Web
- Python Orchestrator
- Shared Object Storage
- Enterprise Nucleus
- TURN/STUN
```

## 3. Omniverse가 담당하지 않는 기능

- 회의 의미 분석은 Gemma가 담당함
- 2D 생성은 GPT Image API가 담당함
- 3D Reconstruction은 Hunyuan3D가 담당함
- 정밀 제조 CAD·STEP·피처 트리는 별도 CadQuery·상용 CAD 계층이 필요함

## 4. 단계별 도입

### Stage 1

OpenUSD 파일 생성과 다운로드를 적용함.

### Stage 2

Kit App에서 Asset Validator·RTX 검토를 적용함.

### Stage 3

Nucleus 게시와 회의실 Live Review를 적용함.

### Stage 4

WebRTC 사용자별 세션 할당·GPU Scheduling을 적용함.

### Stage 5

PhysX Joint·센서·동작 시뮬레이션과 Digital Twin을 추가함.
