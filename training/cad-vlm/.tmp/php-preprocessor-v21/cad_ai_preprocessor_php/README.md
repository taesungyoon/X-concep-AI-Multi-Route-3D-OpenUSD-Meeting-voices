# CAD AI Dataset Studio - PHP

DXF·STEP/STP 파일을 PHP로 검증·파싱하고 Geometry JSON, SVG 미리보기, PLY 포인트클라우드, 품질 보고서, Manifest와 ZIP 학습 패키지를 생성하는 풀스택 참조 구현입니다.

V2.1은 긴 AutoCAD DXF HEADER와 `$DWGCODEPAGE=ANSI_949` 한글을 지원합니다.
사용자 제공 실제 산업 DXF 5개와 STP 2개의 결과는
`docs/actual-cad-validation.md`에 SHA-256과 함께 기록했습니다.

## 요구사항

- PHP 8.2 이상
- extensions: json, fileinfo, mbstring, PDO, pdo_sqlite 또는 pdo_mysql, zip

## 실행

```powershell
$env:PHP_BIN='C:\path\to\php.exe'
.\run.ps1
```

또는:

```bash
php -S 127.0.0.1:8080 -t public router.php
```

브라우저에서 `http://127.0.0.1:8080`을 엽니다.

## 테스트

```bash
php tests/run.php
```

Windows 10,000회 병렬 검증:

```powershell
$env:PHP_BIN='C:\path\to\php.exe'
$env:PHP_INI='C:\path\to\php.ini'
.\tests\validate_10000.ps1 -Iterations 10000 -Workers 8
```

영문 경로 기반 Linux/macOS 환경에서는 `php tests/validate_10000.php`도 사용할 수 있습니다.

## 운영 데이터베이스

로컬 기본값은 SQLite입니다. MySQL/MariaDB는 `CAD_AI_DSN`, `CAD_AI_DB_USER`, `CAD_AI_DB_PASSWORD`를 설정합니다. `database/mysql.sql`은 명시적 배포용 스키마입니다.

## 제한

기본 파서는 ASCII DXF와 STEP Part21 구조·좌표·통계를 추출하는 참조 구현입니다. STEP 설계 이력 복원을 주장하지 않습니다. 정밀 Assembly/B-Rep/Mesh는 OCP 기반 외부 CAD Worker로 확장합니다.
