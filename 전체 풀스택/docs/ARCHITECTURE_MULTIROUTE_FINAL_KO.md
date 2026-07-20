# X concep AI Multi-Route 최종 아키텍처

## 1. 논리 구조

```text
X concep AI Web / Mobile UI
PHP Responsive UI
        ↓
Django REST Framework Control Plane
MySQL · Redis/Celery · Project/Job/Asset/Meeting/Validation
        ↓
NeMo Agent Toolkit Gateway
Rules + Agent Plan + Trace/Evaluation
        ↓
Gemma Requirement Analyzer · Qdrant RAG
        ↓
Design State + Generation Plan
        ↓
┌────────────────────┬────────────────────┬────────────────────┐
│ GPT Image API      │ Hunyuan3D Local    │ OpenSCAD Local     │
│ 2D realism        │ fast/freeform mesh │ parametric structure│
└──────────┬─────────┴──────────┬─────────┴──────────┬─────────┘
           └────────────────────┴────────────────────┘
                              ↓
                        Blender Worker
               Assembly · PBR · Render · USD Bridge
                              ↓
                     GLB · STL · PNG · USD
                              ↓
                    OpenUSD Composition
      Geometry · Looks · Meeting · Revision · Physics
                              ↓
       Omniverse Kit · Validator · Nucleus · WebRTC · PhysX
```

## 2. 설계 원칙

- 기존 GPT Image와 Hunyuan3D 경로를 유지함
- OpenSCAD와 Blender를 추가 선택 경로로 적용함
- 사용자에게 엔진보다 원하는 결과 목적을 노출함
- 모든 엔진은 공통 Design State를 참조함
- 결과를 단일 엔진에 종속하지 않고 Asset Manifest로 관리함
- 자동 Router 오류를 Fallback Graph로 통제함
- Blender를 공통 시각화·자산 변환 Hub로 사용함
- OpenUSD를 자산 구성·Revision·협업 계층으로 사용함
- 생성형 Mesh와 제조 승인 데이터를 검증 등급으로 구분함

## 3. 데이터 계약

### Design State

설계 의도와 일관성 기준임.

### Generation Plan

부품·요청별 생성 경로와 Fallback을 정의함.

### Asset Manifest

실제 생성 파일, 엔진, 버전, 품질 결과와 Hash를 기록함.

### Validation Report

기능·구성·치수·배치·Mesh·OpenUSD 검증 결과와 등급을 기록함.

## 4. 상태 전이

```text
RECEIVED
→ ANALYZED
→ ROUTE_PLANNED
→ PREVIEW_GENERATING
→ PREVIEW_READY
→ QUALITY_VALIDATING
   ├─ PASS → FINAL_PROCESSING
   └─ FAIL → FALLBACK_PROCESSING → QUALITY_VALIDATING
→ FINAL_READY
→ OPENUSD_PACKAGING
→ COMPLETED
```

## 5. 결과 역할

| 결과 | 역할 |
|---|---|
| GPT Image | 시각적 컨셉과 외관 방향임 |
| Hunyuan3D | 빠른 이미지 기반 Mesh임 |
| OpenSCAD | 치수와 구조 기반 파라메트릭 모델임 |
| Blender | 조립·재질·렌더링·애니메이션·USD Bridge임 |
| OpenUSD | 자산·Layer·Revision·Metadata 구성임 |
| Omniverse | RTX 검토·협업·물리·WebRTC 실행 환경임 |
