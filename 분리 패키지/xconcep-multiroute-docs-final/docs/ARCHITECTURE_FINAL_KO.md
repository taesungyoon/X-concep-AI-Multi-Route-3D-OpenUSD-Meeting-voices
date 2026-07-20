# 최종 아키텍처

## 1. 설계 원칙

- GPT Image API만 외부 AI 생성 서비스로 사용함
- 회의 음성·LLM·3D·OpenUSD 처리는 로컬 인프라를 기본으로 함
- PHP는 사용자 UI, 파일 업로드, 프로젝트 상태와 API Gateway를 담당함
- Python은 AI Orchestration과 파일 변환을 담당함
- Omniverse Kit는 웹 서비스의 필수 실행 경로가 아니라 Enterprise 검토·협업·RTX 계층으로 분리함
- 기본 브라우저 3D 미리보기는 GLB와 Three.js로 유지함

## 2. 런타임 구성

```text
[브라우저]
  PHP UI
  MediaRecorder
  Three.js GLB Viewer
       │
       ▼
[PHP Gateway]
  프로젝트 JSON
  이미지·오디오 업로드
  Python API 호출
  다운로드 URL 관리
       │
       ▼
[Python Orchestrator]
  Speech Client
  Meeting Analyzer
  Local Gemma Client
  GPT Image Client
  Hunyuan3D Client
  OpenUSD Exporter
       │
       ├─────────────▶ [vLLM + Ray + Gemma Local]
       ├─────────────▶ [GPT Image API External]
       ├─────────────▶ [Hunyuan3D Local]
       └─────────────▶ [Shared Storage]
                              │
                              ▼
                     [Omniverse Kit App]
                     RTX / PhysX / Variant
                     Validator / Converter
                     Nucleus / Live / WebRTC
```

## 3. 회의 처리 상태

```text
recording_ready
→ transcribing
→ analyzed
→ generating_2d
→ 2d_ready
→ generating_3d
→ completed
```

회의는 15초 단위 WebM 또는 브라우저 지원 오디오 Chunk로 업로드함. Python Speech Client가 전사하고 PHP 프로젝트 JSON에 Segment를 누적함. 사용자가 분석 버튼을 누르면 누적 Transcript를 Gemma에 전달함.

## 4. 데이터 경계

### 외부로 전송되는 데이터

- GPT Image API에 전달하는 정제된 이미지 생성 프롬프트임
- 사용자가 참고 이미지를 제공하고 Image Edit를 사용하는 경우 해당 참고 이미지 또는 Contact Sheet가 전달될 수 있음

### 로컬에 유지되는 데이터

- 원본 회의 음성 파일
- 전체 회의 Transcript
- Gemma 요구사항 분석 JSON
- Hunyuan3D 입력·결과
- GLB·STL·OpenUSD 파일
- Omniverse Nucleus 게시 전 로컬 Stage

## 5. OpenUSD Layer 설계

```text
root.usda
├─ subLayer: geometry.usda
├─ subLayer: looks.usda
├─ subLayer: meeting.usda
└─ subLayer: revisions/rev_XXX.usda
```

- `geometry.usda`: Hunyuan3D GLB에서 추출한 Mesh·Transform 기록함
- `looks.usda`: DisplayColor·재질 연결을 기록함
- `meeting.usda`: 회의 요약, 결정 수, 미확정 수, 프로젝트 ID를 기록함
- `revisions/rev_XXX.usda`: 회의 중간 생성·변경 시점별 Revision Metadata를 기록함
- `root.usda`: Default Prim, Up Axis, metersPerUnit, VariantSet, PhysicsScene을 구성함

## 6. Omniverse 적용 범위

| NVIDIA 기술 | 구현 위치 | 목적 |
|---|---|---|
| Kit SDK | `omniverse-kit/apps` | 전용 검토 앱 구성 |
| OpenUSD | Python Exporter | 장면·Layer·Revision 관리 |
| RTX Viewport | Kit 설정 | 고품질 렌더링 검토 |
| PhysX / UsdPhysics | USD + Kit | 충돌·물리 준비 |
| Asset Converter | Kit Script | GLB·FBX·OBJ → USD 변환 |
| Asset Validator | Kit Script·Extension | USD 품질 검사 |
| Nucleus | 게시 스크립트 | 공유 저장·협업 |
| Live Session | Nucleus 기반 | 다중 사용자 검토 |
| WebRTC Livestream | Kit App | 브라우저 RTX 화면 전송 |
| OV Web SDK | `omniverse-web-client` | 스트림 연결·제어 |
| Speech NIM | 선택 STT Provider | 실시간·오프라인 전사 |

## 7. 의도적 제외

- Omniverse가 정밀 STEP·B-Rep 설계 엔진을 대체하지 않음
- Hunyuan3D 단일 Mesh에서 모터·프레임·센서 의미 구조를 자동 복원하지 않음
- 현재 전달본은 실제 Nucleus 계정·Kit NGC Image·TURN/STUN 인증을 포함하지 않음
- 회의 분석 결과는 설계 확정값이 아니라 사용자 확인이 필요한 요구사항 상태임
