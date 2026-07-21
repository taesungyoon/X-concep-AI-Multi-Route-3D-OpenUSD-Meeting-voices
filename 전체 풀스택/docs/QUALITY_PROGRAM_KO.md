# 1·2·3·4·6단계 지속 품질 프로그램

이 프로그램은 운영 기반(1), 평가 체계(2), 2D 생성 품질(3), CAD 정밀화(4), OpenUSD 협업(6)을 같은 리비전과 같은 표본으로 반복 측정한다. API 키와 외부 사내 DB 없이 `smoke`를 실행할 수 있다.

## 실행

```powershell
cd "전체 풀스택"
python scripts/sync-quality-datasets.py --tier smoke
python scripts/run-quality-program.py --tier smoke
```

캐시만으로 재현하려면 첫 명령에 `--offline`을 추가한다. 표본은 seed `20260721`과 SHA-256 순위로 선택되어 Python 버전과 실행 순서에 의존하지 않는다. 결과는 `storage/quality-program/latest.json`, `latest.md`와 각 실행별 JUnit XML에 기록된다.

## 등급 계약

| 등급 | 용도 | 실제 생성/네이티브 도구 요구 |
|---|---|---|
| `smoke` | PR/주간 재현성, 라이선스, 평가기 준비도 | 생성 결과와 usdchecker는 미측정으로 분리 |
| `standard` | 로컬 운영 후보 승인 | ComfyUI 이미지 결과, 95% 네이티브 CAD, pxr/usdchecker 필수 |
| `full` | 릴리스 후보/연구 성능 증빙 | 이미지 60장, 의미 평가 30건, NIST STEP 17건 필수 |

`not_measured`는 통과로 계산하지 않는다. 다만 해당 등급에서 선택 항목이면 readiness 점수와 별도로 보존한다.

로컬 standard 이미지 실측은 ComfyUI를 실행한 상태에서 아래처럼 수행한다. 고정 표본 12장을 고정 seed로 만들며 OpenAI 키는 사용하지 않는다.

```powershell
python scripts/sync-quality-datasets.py --tier standard --offline
python scripts/benchmark-local-images.py --count 12
python scripts/benchmark-public-cad.py
python scripts/run-quality-program.py --tier standard
```

## 데이터 소스와 권리 정책

- PartiPrompts: Apache-2.0, 1,632개 프롬프트. 카테고리·난제 분포를 고정 표본화한다.
- GenEval: MIT, 553개 메타데이터. 단일/복수 객체, 수량, 색상, 위치, 속성 결합을 다룬다.
- ASWF USD WG assets: CC BY 4.0. 독립형 PrimvarInterpolation USDA를 OpenUSD 호환성 기준으로 사용한다.
- NIST MBE PMI STEP: 제한 없이 사용할 수 있는 CTC/FTC/STC AP242 공식 상호운용성 테스트 17개를 사용한다. ZIP SHA-256, 개별 STEP SHA-256, OpenCascade topology/bounds/solid volume을 검증한다. 각 파일은 별도 프로세스에서 geometry-only STEPControl reader로 격리한다.
- ABC: 약 100만 CAD 모델이지만 원 저작자가 모델 저작권을 보유한다. 법무/내부 권리 검토 전에는 자동 다운로드하지 않는다.
- SketchGraphs: 코드 라이선스와 스케치 데이터 권리가 동일하지 않다. 법무/내부 권리 검토 전에는 자동 다운로드하지 않는다.

리비전과 출처는 `quality/datasets.json`, 실제 받은 파일의 체크섬과 표본 인덱스는 `storage/quality-datasets/quality-datasets.lock.json`이 단일 기준이다.

## 3단계 이미지 결과 계약

`storage/quality-results/images/manifest.jsonl`에 한 줄당 아래 형태로 기록한다.

```json
{"dataset":"parti-prompts","row_index":12,"path":"files/parti-12.png","prompt_sha256":"..."}
```

`path`는 manifest 기준 상대경로 또는 절대경로다. 기본 해상도·용량·entropy·정확 중복률을 항상 측정한다. 의미 평가는 고정된 Grounding DINO base 모델과 별도 보고서를 사용한다.

```powershell
$comfyPython = "$env:USERPROFILE\Documents\ComfyUI\.venv\Scripts\python.exe"
& $comfyPython scripts/score-geneval-owlvit.py --backend grounding-dino
```

평가기는 `IDEA-Research/grounding-dino-base`의 고정 커밋을 사용하며 API 키는 필요 없다. 보고서의 모델·GenEval 원본·이미지 manifest·각 이미지 SHA가 모두 일치해야 점수로 인정한다. 이 값은 휴대 가능한 **GenEval-compatible 지표**이며 공식 GenEval Mask2Former 점수가 아니다. 고정 30건에서 Grounding DINO는 29/30(96.67%), OWL-ViT는 21/30(70.00%, NMS 0.30), DETR는 17/30(56.67%)이었다. full 임계치는 95%다.

full 감사는 다음처럼 실행한다. 이미지 60장과 의미 평가 30건이 모두 현재 manifest에 결합되어야 한다.

```powershell
python scripts/sync-quality-datasets.py --tier full --offline
python scripts/benchmark-public-cad.py
python scripts/run-quality-program.py --tier full
```

OpenAI Image API 실호출은 기존 합의대로 키 입력 직전에 사용자를 호출한 뒤에만 수행한다.

## 해석상 주의

- CAD 95%는 자동화된 25개 OpenSCAD/Blender acceptance 계약이다. 제조 공차, 구조 안전, 인증을 의미하지 않는다.
- NIST 100%는 17개 공개 AP242 파일의 파싱·위상·경계·solid/tessellated 계약이며 PMI 의미 정확도나 제조 인증을 뜻하지 않는다.
- `smoke PASS`는 운영 준비도와 재현성 통과이지 생성 모델의 의미 정확도 95%를 뜻하지 않는다.
- 외부 사내 MySQL 인증은 현재 범위 밖이며, 내부 MySQL에서만 검증한다.
