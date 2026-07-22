# 고급 품질 프로그램

이 문서는 기본 품질 프로그램 위에 추가한 평가 신뢰도, 반복 이미지 생성, STEP round-trip, OpenUSD composition, 운영 복구 계약을 설명한다. 자동화 점수 95%는 소프트웨어 acceptance 계약이며 제조 승인·공차 인증·사람 선호도 95%를 의미하지 않는다.

## 범위와 보류 조건

- 기본 2D 경로: 로컬 ComfyUI/FLUX.2
- 추가 2D 경로: OpenAI Image API. API 키 테스트 전에는 사용자 입력을 기다리며 이 프로그램에서 실행하지 않는다.
- 인증 DB: 내부 Docker MySQL만 사용한다.
- 외부 사내 MySQL과 `corporate_db` 인증은 보류한다.
- 공식 GenEval Mask2Former와 사람 검수는 별도 측정이다. 결과가 없으면 Grounding DINO 호환 점수로 대체했다고 주장하지 않는다.

## 1. 평가 신뢰도

`scripts/analyze-evaluation-reliability.py`는 다음을 측정한다.

- 논리 case 기준 고정 calibration/holdout 분할
- 120개 이상 holdout, 3개 seed
- seed별 점수의 평균·최소·분산·평균 95% 신뢰구간
- 전체 이항 점수의 Wilson 95% 신뢰구간
- 평가기 간 일치율과 Cohen's κ
- 공식 GenEval 및 사람 라벨의 측정 여부

기본 이미지 품질 manifest를 주 평가로 사용하고, GenEval 의미 평가는 별도 source로 추가한다.

```powershell
python scripts/analyze-evaluation-reliability.py `
  --report basic=storage/quality-results/image-holdout/manifest.jsonl `
  --report grounding-dino=storage/quality-results/image-holdout/geneval-raw-holdout.json `
  --prompt-mode raw `
  --minimum-holdout-cases 120 `
  --minimum-seeds 3 `
  --minimum-score-pct 95 `
  --write-human-template storage/quality-results/reliability/human-labels.template.jsonl
```

사람 검수 또는 공식 GenEval을 필수화할 때만 각각 `--require-human`, `--require-official-geneval`을 사용한다.

## 2. 이미지 반복 생성과 A/B

기본 실행은 calibration 30개와 holdout 120개를 선택한다. raw는 3개 seed, rewritten은 첫 seed를 공유해 총 600장을 생성한다. 각 결과 직후 manifest를 원자적으로 저장하고 `--resume`에서 동일 case·prompt mode·benchmark seed만 재사용한다.

```powershell
python scripts/benchmark-image-holdout.py `
  --resume `
  --seeds 20260721,20260722,20260723 `
  --rewritten-seeds 20260721
```

Grounding DINO 의미 평가는 raw/rewritten과 calibration/holdout을 섞지 않는다.

```powershell
python scripts/score-geneval-owlvit.py `
  --image-manifest storage/quality-results/image-holdout/manifest.jsonl `
  --prompt-mode raw --split holdout --minimum-score 0.95 `
  --output storage/quality-results/image-holdout/geneval-raw-holdout.json

python scripts/score-geneval-owlvit.py `
  --image-manifest storage/quality-results/image-holdout/manifest.jsonl `
  --prompt-mode rewritten --split holdout --minimum-score 0.95 `
  --output storage/quality-results/image-holdout/geneval-rewritten-holdout.json

python scripts/compare-image-ab.py `
  --raw-report storage/quality-results/image-holdout/geneval-raw-holdout.json `
  --rewritten-report storage/quality-results/image-holdout/geneval-rewritten-holdout.json `
  --image-manifest storage/quality-results/image-holdout/manifest.jsonl
```

`compare-image-ab.py`는 같은 논리 case와 같은 실제 noise seed인지 확인한 뒤 raw/rewritten 의미 점수, delta, 일치율을 기록한다.

### 2.1 정밀 이미지 라우터 승격 절차

`python-worker/app/image_precision.py`는 모든 요청을 느린 경로로 보내지 않는다.

- `single_object`, 일반 색상, 단순 제품: 기존 `fast` 경로
- 정확한 개수, 다중 객체, 좌우·상하 관계, 객체별 색상: `precision` 경로
- 구조화 요구사항: `image_requirements=[{"class": ..., "count": ..., "color": ..., "position": ...}]`
- 정밀 프롬프트는 정확한 총 객체 수, 분리 배치, 관계, 중복·반사·텍스트 금지를 장면 계약으로 만든다.

승격은 calibration에서 후보를 선택한 뒤 holdout을 한 번만 측정한다. 쉬운 요청은 원본 manifest의 prompt SHA, image SHA, noise seed가 모두 같을 때만 재사용한다.

```powershell
python scripts/benchmark-image-holdout.py `
  --prompt-modes precision --only-split calibration `
  --rewritten-seeds 20260721 `
  --route-reference-manifest storage/quality-results/image-holdout/manifest.jsonl `
  --output storage/quality-results/image-router-calibration

python scripts/benchmark-image-holdout.py `
  --prompt-modes precision --only-split holdout `
  --rewritten-seeds 20260721,20260722,20260723 `
  --route-reference-manifest storage/quality-results/image-holdout/manifest.jsonl `
  --output storage/quality-results/image-router-holdout
```

ComfyUI를 가동하지 않고 저장된 증거만 다시 검증할 때는 `--resume --offline-rescore`를 함께 사용한다. 증거가 하나라도 빠졌으면 새로 생성하지 않고 실패한다.

원본과 정밀 후보가 다른 manifest에 있을 때도 동일 시드를 확인할 수 있다.

```powershell
python scripts/compare-image-ab.py `
  --raw-report storage/quality-results/image-holdout/geneval-raw-holdout.json `
  --candidate-report storage/quality-results/image-router-holdout/geneval-precision-holdout.json `
  --raw-manifest storage/quality-results/image-holdout/manifest.jsonl `
  --candidate-manifest storage/quality-results/image-router-holdout/manifest.jsonl `
  --candidate-mode precision --minimum-pairs 120
```

현재 고정 홀드아웃 결과는 다음과 같다.

- 순수 raw Grounding DINO 호환 점수: 89.68%
- 순수 precision 점수: 92.06%
- precision 우선, 검증 실패 시 동일 시드 raw fallback 시스템 점수: 98.41% (124/126)
- 시드별 최저 시스템 점수: 95.24%
- 기본 이미지 품질: 360/360
- calibration 동일 시드: raw 91.67% → precision router 100%

시스템 점수는 Grounding DINO가 후보 선택과 채점에 모두 사용된 `verifier-assisted` 점수이며 독립 평가가 아니다. `image-router-selected/report.json`은 이를 `independent_evaluation=false`로 기록한다. 순수 precision 보고서도 삭제하거나 대체하지 않는다. 사람 검수 또는 공식 GenEval 독립 평가는 별도 후속 측정이다.

## 3. CAD와 PMI

- `benchmark-cad-roundtrip.py`: 판재, 브래킷, 스페이서, 2부품 조립체 60건
- 검증값: STEP export/import 전후 solid 수, 원형 edge 수, bbox, 체적, 조립체 간섭 체적
- 합격 기준: 95% 이상
- 현재 검증: 60/60
- `benchmark-public-cad.py`: NIST AP242 17건 형상, PMI dimension/tolerance/datum/annotation, Part 21 참조 무결성
- 현재 검증: 17/17

대표 STEP은 CAD skill의 `refs --facts --planes --positioning`과 snapshot으로 별도 시각 검토한다. CAD Viewer 설치본에는 문서가 요구하는 `agent:start` npm script가 없으므로 live viewer 링크 생성은 현재 불가하며 CLI와 snapshot을 증빙으로 사용한다.

## 4. OpenUSD

`benchmark-openusd-advanced.py`는 다음 6개 계약을 실제 pxr stage 재개방으로 검사한다.

- Blender → texture material USD export → Blender reload
- variant, sublayer, Z-up, metersPerUnit
- 강·약 layer conflict 해소
- internal-reference instancing
- reference composition
- payload composition

현재 검증은 6/6이다. Blender 5.2에서 제거된 `export_textures` 인자는 호환 fallback으로 처리하며, source `.usda/.usd/.usdc` 형식을 복사할 때 실제 확장자를 보존한다.

## 5. 운영 자동화

- `.github/workflows/quality-program.yml`: 매주 월요일 smoke 회귀, baseline 하락 시 자동 실패, 이전/현재 보고서 업로드
- `compare-quality-baseline.py`: CI smoke 계약과 로컬 advanced 계약 분리
- `capture-quality-environment.py`: 데이터 lock, 모델 SHA-256, workflow source SHA-256, Python/package/native tool/GPU 버전 기록
- `run-comfyui-supervised.ps1`: health 실패·프로세스 종료 재시작, CUDA OOM 시 `normalvram`, 상태 JSON 기록
- `run-image-semantic-verifier.ps1`: 고정 Grounding DINO 리비전을 로컬 CUDA/CPU 서비스로 기동하고 health를 확인
- `smoke-image-semantic-routing.py`: 실제 ComfyUI 생성과 의미 검증기를 연결해 동일 noise seed 정밀→raw fallback을 검증
- `verify-mysql-backup.py`: 내부 MySQL 백업, 격리 DB 복원, 모든 테이블의 정확한 row count 비교, 검증 DB 삭제
- `QualityEvidence`: 품질 suite, pass/fail, 점수, 목표, 평가기·모델, 보고서 경로와 SHA-256을 내부 MySQL에 보존
- `import_quality_evidence`: STORAGE_PATH 안의 UTF-8 JSON 보고서만 적재하며 `(suite, report SHA)`로 중복 적재 방지

내부 MySQL 복구 드릴은 품질 증거 테이블을 포함한 16개 테이블이 일치해 통과했다. SQL 백업과 보고서는 `storage/backups/mysql/`에 남고 `xconcep_restore_verify` DB는 실행 후 삭제된다.

2026-07-22 운영 smoke에서는 홀드아웃의 `four computer keyboards` 사례와 seed `1178368085068869730`을 사용했다. 독립 재기동을 포함한 두 번의 실제 실행에서 모두 정밀 후보는 검증기가 5개로 감지해 실패했고, 같은 실행·같은 seed의 raw 후보는 정확히 4개로 검증되어 선택됐다. 실행 시간은 각각 62.031초와 131.032초였으며 최신 증거는 `storage/quality-results/runtime-semantic-smoke/report.json`에 양쪽 판정, 동일 seed, 모델 리비전, 이미지·manifest SHA-256을 기록한다.

두 실행의 최종 이미지 SHA-256은 서로 달랐다. GPU/CUDA 생성에서 같은 seed는 정밀·raw 후보를 공정하게 비교하는 페어링 조건이지 재기동 간 bit-exact 출력 보증이 아니다. 합격 계약은 seed 동일성, 구조 품질, 의미 판정, route 선택이며 비트 단위 결정성으로 해석하지 않는다. 이 smoke도 같은 평가기가 선택과 판정에 사용되므로 독립 평가가 아니다.

```powershell
powershell -ExecutionPolicy Bypass -File scripts/run-comfyui-supervised.ps1 -DurationSeconds 600
powershell -ExecutionPolicy Bypass -File scripts/run-image-semantic-verifier.ps1 -DurationSeconds 600
python scripts/smoke-image-semantic-routing.py --require-raw-fallback
```

로컬 advanced 전체 계약은 다음 명령으로 확인한다.

```powershell
python scripts/compare-quality-baseline.py --contract quality/advanced-baseline.json
```

최종 의미 보고서를 내부 MySQL에 등록하는 명령은 다음과 같다. 외부 인증 DB에는 기록하지 않는다.

```powershell
docker compose exec -T control-plane python manage.py import_quality_evidence `
  --suite image-semantic-precision `
  --report quality-results/image-router-holdout/geneval-precision-holdout.json `
  --target-pct 95
```

운영 fallback smoke 증거는 점수형 성능 표본과 분리해 다음 suite로 추가 적재한다.

```powershell
docker compose exec -T control-plane python manage.py import_quality_evidence `
  --suite runtime-image-semantic-routing `
  --report quality-results/runtime-semantic-smoke/report.json `
  --target-pct 95
```

## 증빙 위치

- 이미지: `storage/quality-results/image-holdout/`
- 실제 운영 라우팅: `storage/quality-results/runtime-semantic-smoke/report.json`
- 신뢰도: `storage/quality-results/reliability/`
- 환경 lock: `storage/quality-results/environment-lock.json`
- CAD round-trip: `storage/benchmarks/cad-roundtrip/latest.json`
- NIST PMI: `storage/benchmarks/public-cad-nist/latest.json`
- OpenUSD: `storage/benchmarks/openusd-advanced/latest.json`
- MySQL 복구: `storage/backups/mysql/latest.json`
