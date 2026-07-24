# 문서 관리
| 항목 | 내용 |
|---|---|
| 문서명 | DXF·STEP 기반 AI 학습 데이터 전처리 PHP 풀스택 프로그램 매뉴얼 |
| 버전 / 기준일 | V2.1 / 2026-07-23 |
| 주 개발 언어 | PHP 8.2 이상, 검증 런타임 PHP 8.4.23 |
| 프론트엔드 | HTML5, CSS3, Vanilla JavaScript |
| 데이터베이스 | 로컬 SQLite, 운영 MySQL/MariaDB |
| 대상 | PHP 개발자, 데이터 엔지니어, CAD 담당자, ML 엔지니어, 운영자 |
| 구현 위치 | cad_ai_preprocessor_php |

>GOOD|최종 구현 상태|Python 참조 구현을 대체하는 PHP 풀스택 표준 준수본이다. DXF·STEP 업로드부터 전처리 패키지, 웹 화면, 데이터베이스, 기준 모델까지 PHP로 연결하고 실제 산업 DXF 5개와 STP 2개를 수용했다.

# 목차
:::toc

:::part|PART I|프로그램 개요와 빠른 시작|PHP 표준 구현의 범위와 실행 방법을 확인한다.

# 1. 목적
CAD AI Dataset Studio PHP는 DXF·STEP/STP 파일을 안전하게 등록하고 공통 Geometry JSON, SVG 미리보기, PLY 포인트클라우드, 품질 보고서, Label·Metadata, Manifest와 ZIP 학습 패키지를 생성한다. 완료된 라벨 샘플은 최근접 중심 기준 모델까지 연결하여 데이터 계약과 학습 입력의 정상 여부를 검증한다.

## 1.1 해결 과제
- CAD 형식마다 달라지는 추출 결과를 공통 데이터 계약으로 통일
- 원본·파생물·모델 입력의 sample_id·SHA-256·버전 추적
- 중복·손상·빈 형상·무라벨·경계 누락의 조기 탐지
- 동일 개정군이 서로 다른 데이터 분할에 포함되는 누수 방지
- PHP 운영 조직에서 설치·검토·배포할 수 있는 단일 풀스택 제공

## 1.2 구현 범위
| 영역 | 기본 PHP 구현 | 생산 확장 |
|---|---|---|
| DXF | ASCII 그룹 코드, 엔티티·레이어·문자·경계 | ezdxf Worker, 블록·치수·복구 |
| STEP | Part21 엔티티·제품명·점·위상 통계 | OCP Worker, Assembly·B-Rep·물성 |
| 파생물 | JSON, SVG, PLY, Quality, Manifest, ZIP | Mesh, 멀티뷰 PNG, Parquet |
| 학습 | PHP 최근접 중심 기준 모델 | PyTorch/GNN/멀티모달 모델 |
| DB | SQLite 또는 PDO MySQL/MariaDB | HA DB, 읽기 복제, 감사 저장소 |

>WARN|정확성 경계|STEP 교환 파일에서 원 CAD의 설계 이력과 피처 트리를 완전히 복원할 수 없다. topology·surface 통계와 추론 피처는 설계 의도와 구분한다.

# 2. 빠른 시작
## 2.1 필수 환경
- PHP 8.2 이상
- json, fileinfo, mbstring, PDO, pdo_sqlite 또는 pdo_mysql, zip 확장
- Windows PowerShell 또는 Linux Shell

## 2.2 Windows
```powershell
$env:PHP_BIN='C:\path\to\php.exe'
.\run.ps1
```

## 2.3 PHP 직접 실행
```bash
php -S 127.0.0.1:8080 -t public router.php
```

## 2.4 Docker
```bash
docker compose up --build
```

브라우저에서 http://127.0.0.1:8080 을 열고 samples/simple.dxf와 samples/simple.step을 등록한다.

---PAGE---
:::part|PART II|사용 언어와 구조|PHP 표준, 컴포넌트 경계, 상태 흐름을 이해한다.

# 3. 사용 언어·기술
| 구분 | 언어·기술 | 적용 |
|---|---|---|
| 백엔드 | PHP 8.2+ | API, 검증, 파싱, 전처리, 품질, 패키징, 학습 |
| 프론트엔드 | HTML5, CSS3, JavaScript | 대시보드, 업로드, 조회, 상세, 학습 |
| DB | PDO SQLite / PDO MySQL | 작업·산출물·학습 실행 영속화 |
| 스키마 | JSON Schema | Geometry·Manifest 구조 |
| 데이터 | JSON, JSONL, PLY, SVG, ZIP | 학습 데이터와 파생물 |
| 실행 | PowerShell, Shell | 로컬 실행·검증 |
| 배포 | Dockerfile, Compose YAML | PHP·MariaDB 컨테이너 |
| 의존성 | Composer | PSR-4, PHP 확장, PHPUnit 선택 |

## 3.1 PHP 기준
- declare(strict_types=1)을 모든 PHP 소스에 적용한다.
- PSR-4 네임스페이스와 역할별 클래스를 사용한다.
- SQL은 PDO Prepared Statement로 실행한다.
- 환경 변수로 DSN, 비밀, 포트, 업로드 한도를 주입한다.
- 외부 입력은 형식·길이·크기·경로를 검증한 후 사용한다.
- 사용자 문자열은 JavaScript textContent로 출력한다.

# 4. 아키텍처
```text
[HTML/CSS/JavaScript]
          │ multipart + JSON
          ▼
[PHP Front Controller / HttpApp]
          │
          ├─ UploadValidator · API Key · CSP · Request ID
          ├─ PDO Repository ─ SQLite / MySQL·MariaDB
          ├─ DatasetPipeline
          │    ├─ DxfParser / StepParser
          │    ├─ Normalize / SVG / PLY / Quality
          │    └─ Manifest / ZIP / Artifact registry
          └─ BaselineTrainer
```

## 4.1 주요 소스
| 경로 | 책임 |
|---|---|
| public/index.php | PHP Front Controller |
| src/HttpApp.php | HTTP 라우팅·응답·보안 |
| src/DatasetPipeline.php | 전처리 단계 조정 |
| src/Parsers | DXF·STEP 참조 파서 |
| src/Repository.php | Prepared Statement 저장소 |
| src/BaselineTrainer.php | 최근접 중심 기준 모델 |
| public/assets | HTML/CSS/JavaScript 화면 |
| tests | 단위·통합·10,000회 검증 |

# 5. 상태 흐름
```text
queued → validating → parsing → normalizing
       → quality_check → packaging → completed
오류 → failed + error_code + 사용자 메시지
```

현재 참조 구현은 한 요청 안에서 단계를 동기 처리하되 상태를 모두 DB에 기록한다. 대용량 생산 환경에서는 같은 계약을 유지한 채 Redis/Celery 또는 메시지 큐와 외부 PHP Worker로 분리한다.

---PAGE---
:::part|PART III|입력과 전처리|DXF·STEP 검증, 파싱, 정규화, 패키지를 설명한다.

# 6. 업로드 검증
| 검증 | 기준 | 오류 |
|---|---|---|
| 확장자 | .dxf, .step, .stp | unsupported_extension |
| 크기 | 기본 50MB, 1~2048MB 설정 범위 | invalid_size |
| 텍스트 | NUL이 없는 텍스트 CAD | binary_or_corrupt |
| DXF 시그니처 | 시작 그룹 0/SECTION/2/HEADER | invalid_signature |
| STEP 시그니처 | ISO-10303-21 | invalid_signature |
| 파일명 | basename, 최대 255자 | invalid_filename |
| 저장명 | cryptographic random 32 hex | 서버 생성 |

원래 파일명은 메타데이터로만 보존한다. 원본은 instance/source 아래 난수 저장명으로 복사하고 SHA-256을 기록한다.

# 7. DXF 처리
PHP DxfParser는 그룹 코드 쌍을 순차 해석한다. LINE, CIRCLE, ARC, LWPOLYLINE, POLYLINE, VERTEX, TEXT, MTEXT, INSERT, DIMENSION, POINT, SPLINE을 인식하고 레이어·문자·좌표·경계를 산출한다. `$DWGCODEPAGE=ANSI_949` 도면은 CP949 문자값을 UTF-8로 변환한다. 실제 AutoCAD 파일처럼 ENTITIES가 긴 HEADER·TABLES 뒤에 있어도 시작 그룹을 기준으로 수용한다.

## 7.1 출력
- parser_mode=php_ascii_dxf_v1
- entity_counts, layers, texts
- points, line/circle primitives
- bbox min/max/extent
- 지원 엔티티가 없을 때 warnings

# 8. STEP 처리
PHP StepParser는 ISO 10303-21 레코드의 엔티티 유형, PRODUCT 이름, CARTESIAN_POINT 좌표를 추출한다. EDGE/FACE/SHELL/SOLID와 주요 곡면 계열을 통계화한다.

## 8.1 출력
- parser_mode=php_part21_step_v1
- entity_counts, products, points, bbox
- topology: edge/face/shell/solid
- surfaces: plane/cylinder/cone/sphere/torus/bspline

>RISK|STEP 제한|기본 PHP 파서는 Part21 구조 통계용이다. 정밀 형상 연산, Boolean, Assembly, 물성, 균일 표면 Mesh는 OCP/Open CASCADE Worker를 사용한다.

# 9. 공통 정규화
Geometry JSON은 원 좌표와 bbox를 보존하고 중심·스케일·단위 상태를 기록한다. 단위가 없으면 unknown으로 유지하며 임의 변환하지 않는다.

| 필드 | 의미 |
|---|---|
| schema_version | 데이터 계약 버전 |
| sample_id | 모든 산출물의 공통 키 |
| source | 형식·원본명·SHA-256·크기 |
| entity_counts | 형식별 관측 엔티티 통계 |
| bbox | 원 좌표 경계 |
| normalization | center, scale, units |
| provenance | 구현 언어·버전·생성 시각 |

# 10. 학습 패키지
```text
<job-id>.zip
├─ source/original.<ext>
├─ geometry/geometry.json
├─ images/preview.svg
├─ pointcloud/points_256.ply
├─ features/baseline_vector.json
├─ metadata/metadata.json
├─ metadata/label.json
├─ quality/report.json
├─ manifest.json
└─ manifest.jsonl
```

---PAGE---
:::part|PART IV|데이터 품질과 학습|품질 게이트, 그룹 분할, 기준 모델을 운영한다.

# 11. 품질 점수
점수는 0~1 범위다. 파싱 형상, bbox, 라벨, 설명을 확인하며 경고와 함께 저장한다.

| 조건 | 감점 | 경고 |
|---|---|---|
| 지원 형상 없음 | 0.35 | geometry_empty |
| bbox 없음 | 0.20 | bbox_missing |
| unlabeled | 0.10 | label_missing |
| 설명 없음 | 0.03 | description_missing |

권장 게이트는 0.90 이상 자동 승인 후보, 0.70~0.89 검토, 0.70 미만 격리다. 실제 정책은 데이터 버전과 함께 관리한다.

# 12. 데이터 분할
project_group을 SHA-256 해시 버킷으로 변환해 train 80%, validation 10%, test 10%에 결정적으로 배치한다.

- 같은 개정군은 같은 project_group을 사용한다.
- 원본과 모든 파생물은 동일 split을 공유한다.
- 행 단위 무작위 분할을 금지한다.
- 그룹 정책과 알고리즘 버전을 Manifest에 기록한다.

# 13. 기준 모델
PHP BaselineTrainer는 엔티티·레이어·제품·문자·점·bbox·위상·곡면 통계를 14차원 벡터로 만든다. 전체 벡터를 표준화하고 클래스별 중심을 계산하여 가장 가까운 중심으로 분류한다.

## 13.1 목적
- PHP 전처리 결과가 학습 코드까지 연결되는지 확인
- 라벨 분리도와 데이터 계약 회귀를 빠르게 탐지
- 운영 모델 개발 전 기준선 제공

## 13.2 지표 해석
training_accuracy는 학습 샘플 재분류 결과다. evaluation_scope는 resubstitution_only_not_validation이며 일반화 성능으로 해석하지 않는다.

---PAGE---
:::part|PART V|웹과 API|화면 사용법과 연동 계약을 정의한다.

# 14. 웹 화면
## 14.1 파일 등록
파일, category, project_group, description을 입력한다. 라벨이 없으면 unlabeled이며 기준 학습에서 제외된다.

## 14.2 작업 현황
파일명, 형식, 상태·진행률, 품질, split, 등록 시각을 표시한다. 상세 모달에서 미리보기와 10개 산출물, ZIP 다운로드를 확인한다.

## 14.3 기준 학습
완료된 라벨 샘플이 2개 클래스 이상 있어야 한다. 실행 결과에서 샘플 수·클래스 수·evaluation_scope를 확인한다.

# 15. API
응답은 ok, data, error, meta.request_id 구조다. API Key를 설정하면 X-API-Key 헤더를 사용한다.

| 메서드 / 경로 | 기능 |
|---|---|
| GET /api/health | PHP 런타임·서비스 상태 |
| GET /api/jobs | 작업 목록 |
| POST /api/jobs | multipart CAD 등록·전처리 |
| GET /api/jobs/{id} | 작업·산출물 상세 |
| POST /api/jobs/{id}/retry | 저장 원본으로 새 작업 재처리 |
| GET /api/jobs/{id}/artifact | 등록 산출물 조회 |
| GET /api/jobs/{id}/download | ZIP 다운로드 |
| GET /api/datasets/manifest | JSONL Manifest |
| GET /api/training/runs | 학습 실행 목록 |
| POST /api/training/runs | PHP 기준 모델 학습 |
| GET /api/training/runs/{id} | 학습 실행 상세 |

## 15.1 등록 예시
```bash
curl -F "file=@samples/simple.dxf" \
  -F "category=bracket" \
  -F "project_group=revision-a" \
  -F "description=DXF sample" \
  http://127.0.0.1:8080/api/jobs
```

## 15.2 오류 처리
- HTTP 상태와 error.code를 함께 확인한다.
- request_id로 PHP 오류 로그를 상관 분석한다.
- 내부 클래스명·스택·DB 정보는 사용자 응답에 포함하지 않는다.
- 재처리는 새로운 작업으로 수행하고 원본 해시를 연결한다.

---PAGE---
:::part|PART VI|데이터베이스와 배포|SQLite 개발 환경과 MySQL 운영 환경을 전환한다.

# 16. 데이터베이스
## 16.1 테이블
| 테이블 | 역할 |
|---|---|
| jobs | 업로드, 상태, 품질, split, 패키지 |
| artifacts | 상대 경로, MIME, 크기, SHA-256 |
| training_runs | 알고리즘, 샘플·클래스, 모델, 지표 |

외래 키와 UNIQUE(job_id, relative_path)를 적용한다. MySQL/MariaDB 스키마는 database/mysql.sql에 제공한다.

## 16.2 DSN
```text
SQLite: sqlite:<instance>/cad_ai.sqlite3
MySQL : mysql:host=db;dbname=cad_ai;charset=utf8mb4
```

## 16.3 환경 변수
| 변수 | 기본값 | 설명 |
|---|---|---|
| CAD_AI_HOST | 127.0.0.1 | 바인딩 주소 |
| CAD_AI_PORT | 8080 | 서비스 포트 |
| CAD_AI_INSTANCE | ./instance | 실행 데이터 루트 |
| CAD_AI_MAX_UPLOAD_MB | 50 | 업로드 한도 |
| CAD_AI_API_KEY | 빈 값 | 선택형 API Key |
| CAD_AI_DSN | SQLite | PDO DSN |
| CAD_AI_DB_USER | 빈 값 | DB 사용자 |
| CAD_AI_DB_PASSWORD | 빈 값 | DB 비밀번호 |

# 17. Docker 배포
Compose 구성은 PHP 8.4 CLI 애플리케이션과 MariaDB 11을 실행한다. 운영에서는 비밀번호를 Secret Manager로 이동하고 TLS 프록시, PHP-FPM, 비동기 Worker, 객체 저장소를 적용한다.

## 17.1 배포 체크
- [ ] PHP expose_php와 display_errors를 끈다.
- [ ] TLS·API 인증·요청 크기 제한을 적용한다.
- [ ] instance와 DB 백업·복구를 시험한다.
- [ ] 업로드 저장소 실행 권한을 제거한다.
- [ ] 디스크·큐·실패율·품질 분포 경보를 설정한다.
- [ ] CAD 파일 보존·파기·접근 정책을 승인한다.

---PAGE---
:::part|PART VII|보안과 운영|공격 경계, 관측, 장애 대응을 표준화한다.

# 18. 보안 통제
| 통제 | 구현 |
|---|---|
| 업로드 | 확장자·크기·NUL·시그니처 |
| 저장 | 난수 저장명·SHA-256 |
| 경로 | .. 차단·realpath 작업 루트 검증 |
| SQL | PDO Prepared Statement |
| 브라우저 | textContent, CSP, frame deny, nosniff |
| 인증 | 선택형 X-API-Key, 운영 상위 인증 |
| 오류 | 사용자 메시지와 내부 로그 분리 |

운영에서는 ClamAV, WAF, Rate Limit, 감사 로그, 객체 저장소 잠금, KMS를 추가한다.

# 19. 관측
- 요청 수·오류율·request_id
- 단계별 처리 시간과 실패 코드
- 형식·파서 버전별 품질 점수
- 큐 길이·가장 오래 대기한 작업
- 저장 용량·중복률·무라벨률
- 학습 클래스 분포·데이터 드리프트

# 20. 장애 대응
1. request_id와 job_id를 확보한다.
2. health, PHP 로그, DB, 디스크를 확인한다.
3. 실패 단계와 error_code를 분류한다.
4. 원본을 격리하고 최소 재현 자료를 만든다.
5. 수정 후 단위·API·회귀 검증을 실행한다.
6. 영향·원인·조치·재발 방지를 기록한다.

---PAGE---
:::part|PART VIII|검증과 인수|10,000회 근거와 최종 완료 조건을 확인한다.

# 21. 테스트 구조
각 반복 회차는 다음 4개 테스트를 독립 작업공간에서 실행한다.

| 테스트 | 실제 검증 |
|---|---|
| DXF parser and validation | 엔티티·레이어·경계, 긴 HEADER, CP949 한글, 잘못된 확장자 거부 |
| STEP parser and topology | 제품·점·bbox·위상 통계 |
| Full dataset package | SQLite, 2개 업로드, 10개 산출물, ZIP·Manifest, 품질 |
| Baseline training | 2샘플·2클래스 학습, 저장 모델 재예측 |

## 21.1 실행 명령
```powershell
$env:PHP_BIN='C:\path\to\php.exe'
$env:PHP_INI='C:\path\to\php.ini'
.\tests\validate_10000.ps1 -Iterations 10000 -Workers 8
```

# 22. 최종 10,000회 결과
| 항목 | 결과 |
|---|---|
| 성공 회차 | 10000/10000 |
| 총 테스트 | 40,000건 |
| 통과율 | 100.00% |
| 실패 회차 | 0 |
| 병렬 Worker | 8 |
| 총 소요 시간 | 1355.362초 |
| 회차 P95 | 2.933560초 |
| 소스 SHA-256 | f15fb48a67e232fa58f5929465f658dee22d4b35c557224cd03aeff08b8c3c86 |

>NOTE|검증 범위의 의미|10,000회는 최소 ASCII DXF·STEP 고정 샘플과 긴 DXF HEADER·CP949 한글 회귀 조건에 대한 기능·반복 안정성 검증이다. 실제 산업 도면 7개는 아래 수용 시험으로 별도 검증했다. 바이너리 DXF와 정밀 B-Rep 성능은 범위 밖이다.

# 23. 실제 산업 도면 수용 시험
사용자가 제공한 DXF 5개와 STP 2개를 수정된 PHP 파이프라인에 직접 입력했다.

| 파일 | 처리 결과 | 주요 관측 |
|---|---|---|
| 01-(1).dxf | 엔티티 1,258 · 품질 1.0 | LINE 931, CIRCLE 196, 4 layers |
| 01-(2).dxf | 엔티티 956 · 품질 1.0 | LINE 663, TEXT 112, SPLINE 89 |
| 01-(3).dxf | 엔티티 100 · 품질 1.0 | LINE 44, TEXT 19, DIMENSION 17 |
| 01-(4).dxf | 엔티티 69 · 품질 1.0 | LINE 35, TEXT 19 |
| 01-(5).dxf | 엔티티 973 · 품질 1.0 | LINE 668, CIRCLE 154, ARC 88 |
| speed control unit.stp | 엔티티 87,113 · 품질 1.0 | 점 25,026, 면 6,564, Solid 5 |
| speed controller box.stp | 엔티티 1,384 · 품질 1.0 | 점 226, 면 129, Solid 2 |

7개 모두 경계상자와 형상 통계를 추출하고 파일당 10개 산출물 및 ZIP을 생성했다. 결과는 docs/actual-cad-validation.md에 SHA-256과 함께 기록했다.

>GOOD|실제 도면 결과|7/7 완료, 실패 0, 경고 0, 품질 1.0, ZIP 7/7 정상이다. 검증 과정에서 긴 DXF HEADER 오탐과 ANSI_949 한글 JSON 오류를 발견해 수정했다.

>WARN|품질점수 해석|품질 1.0은 데이터 계약 완료를 뜻한다. 설계 정확성, 공차, 조립 간섭, 제조 가능성 또는 원 CAD 피처 트리의 정확성을 판정하지 않는다.

# 24. 별도 통합 검증
- PHP 8.4.23 구문 검사 전체 통과
- 실제 HTTP health, DXF·STEP multipart 등록, 작업 상세, artifact, ZIP, Manifest 확인
- PHP 기준 모델 2샘플·2클래스 완료
- 브라우저 대시보드·상세 모달·미리보기·산출물 링크 확인
- 파일 누락 422, 허용되지 않은 확장자 422, 경로 이탈 400 확인
- CSP, frame deny, nosniff, no-referrer, request_id 확인

# 25. 인수 체크리스트
## 25.1 기능
- [ ] DXF·STEP/STP 등록과 PHP 파싱이 동작한다.
- [ ] 10개 산출물과 ZIP이 생성된다.
- [ ] DB 상태·artifact·학습 실행이 추적된다.
- [ ] 같은 그룹의 split이 결정적이다.
- [ ] PHP 기준 모델이 생성되고 재예측된다.

## 25.2 보안·운영
- [ ] 업로드·경로·SQL·브라우저 입력 통제가 적용된다.
- [ ] 비밀·내부 예외·절대 경로를 외부 응답에 노출하지 않는다.
- [ ] TLS·인증·백업·경보·보존 정책이 적용된다.
- [ ] inferred 정보에 근거·신뢰도·버전을 기록한다.

## 25.3 문서·검증
- [ ] 최종 소스 해시와 10,000회 보고서가 일치한다.
- [ ] 제공된 실제 산업 CAD 7개 수용 결과와 SHA-256이 확인됐다.
- [ ] 운영 DSN과 Secret이 배포 환경에 설정됐다.
- [ ] 복구 절차와 담당자가 인계됐다.

# 26. 결론
본 프로그램은 업로드 개발 표준의 PHP 기준에 맞춰 백엔드, 프론트엔드, DB, CAD 전처리, 품질, 패키지, 기준 학습을 하나의 추적 가능한 풀스택으로 연결한다. 기본 구현은 재현 가능한 데이터 계약 검증에 집중하며, 계약을 유지한 채 MySQL/MariaDB, PHP-FPM, 비동기 Worker, 객체 저장소와 OCP CAD 엔진으로 확장한다.

>GOOD|최종 원칙|관측 정보와 추론 정보를 분리하고, 원본부터 모델 입력까지 sample_id·SHA-256·schema_version으로 추적하며, 최소 샘플의 학습 정확도를 운영 성능으로 해석하지 않는다.

본 문서는 PHP 소스와 데이터 계약이 변경될 때 함께 개정한다.
