# 시스템 아키텍처

## 1. 서비스 경계

```text
Browser
  │
  ▼
PHP Web / API Gateway
  ├─ 업로드 검증
  ├─ 프로젝트 JSON 저장
  ├─ 작업 이력
  └─ Python Worker 호출
        │
        ▼
Python FastAPI Orchestrator
  ├─ LocalGemmaClient
  ├─ GPTImageClient
  ├─ Hunyuan3DClient
  ├─ STL Converter
  ├─ Preview Renderer
  └─ OpenUSD Exporter
```

## 2. 외부·내부 통신 구분

| 계층 | 실행 위치 | 외부 인터넷 |
|---|---|---|
| PHP Web | 로컬/사내 서버 | 불필요 |
| 사용자 보유 Gemma 계열 커스텀 64B + vLLM + Ray | 로컬 GPU 클러스터 | 모델 설치 이후 불필요 |
| GPT Image API | OpenAI API | 필요 |
| Hunyuan3D 2.1 | 로컬 GPU 서버 | 모델 설치 이후 불필요 |
| OpenUSD 변환 | 로컬 Python Worker | 불필요 |
| Three.js Viewer | 사용자 브라우저 | 불필요 |

## 3. 2D 생성 흐름

1. PHP가 프롬프트와 업로드 이미지를 저장함.
2. Python Worker가 Gemma에 텍스트와 이미지 Data URI를 전달함.
3. Gemma는 요구사항 JSON과 서로 다른 컨셉 프롬프트 4개를 생성함.
4. 참고 이미지가 있으면 Python Worker가 2×2 Contact Sheet로 정리함.
5. GPT Image API의 생성 또는 편집 경로를 호출함.
6. 생성 이미지를 프로젝트 `concepts/`에 저장함.
7. 사용자가 4개 중 하나를 선택함.

## 4. 3D 생성 흐름

1. 선택된 2D 이미지를 Base64로 변환함.
2. 로컬 Hunyuan3D `/generate` API에 전달함.
3. Binary 또는 JSON 응답에서 GLB를 저장함.
4. Trimesh가 GLB를 STL로 변환함.
5. Blender가 설정된 경우 Headless PNG 렌더를 수행함.
6. Blender 미설정 시 선택된 2D 이미지를 안내형 Preview로 사용함.
7. GLB Scene을 OpenUSD USDA로 변환함.
8. `usd-core`가 설치된 경우 USDC도 생성함.

## 5. 파일 구조

```text
storage/projects/PRJ-.../
├─ project.json
├─ analysis.json
├─ uploads/
├─ concepts/
│  ├─ concept-1.png
│  ├─ concept-2.png
│  ├─ concept-3.png
│  └─ concept-4.png
└─ result/
   ├─ model.glb
   ├─ model.stl
   ├─ model.usda
   ├─ model.usdc        # usd-core 사용 시
   └─ render.png
```

## 6. 장애 분리

- GPT Image API 장애는 2D 생성 단계에만 영향을 줌.
- Gemma 장애는 요구사항 분석 단계에만 영향을 줌.
- Hunyuan3D 장애는 3D 생성 단계에만 영향을 줌.
- USDC 생성 실패 시 USDA는 계속 제공함.
- PHP API는 Python 절대경로를 외부 응답에서 제거함.
