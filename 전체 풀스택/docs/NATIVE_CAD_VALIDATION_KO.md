# Blender / OpenSCAD 네이티브 운영 및 검증 가이드

## 현재 기준 버전

- Blender 5.2.0 LTS Windows x64
- OpenSCAD 2021.01 Windows x64
- 설치 위치: 저장소 루트의 `.native-tools/`
- 소스: Blender 및 OpenSCAD 공식 릴리스 서버
- 무결성: 설치 스크립트가 고정된 SHA-256 해시를 검증한 뒤만 압축을 풀다.

Blender는 사용자 프로필 쓰기 권한에 의존하지 않도록 `portable/` 프로필로 실행한다. 두 도구는 Python 대체 모형이 아닌 실제 Windows 네이티브 바이너리다.

## 설치와 확인

PowerShell에서 저장소 루트를 기준으로 실행한다.

```powershell
powershell -ExecutionPolicy Bypass -File ".\전체 풀스택\scripts\setup-native-cad.ps1"
```

이미 설치된 파일과 버전만 확인하려면 다음을 실행한다.

```powershell
powershell -ExecutionPolicy Bypass -File ".\전체 풀스택\scripts\setup-native-cad.ps1" -VerifyOnly
```

`settings.py`는 `.native-tools`, PATH, Program Files 순으로 네이티브 파일을 자동 탐색한다. 명시적으로 고정할 때는 다음 환경변수를 사용한다.

```text
OPENSCAD_MODE=native
OPENSCAD_BIN=C:\...\.native-tools\openscad-2021.01\openscad.com
BLENDER_MODE=native
BLENDER_BIN=C:\...\.native-tools\blender-5.2.0-windows-x64\blender.exe
```

`native`는 실패를 숨기지 않고 요청을 실패로 처리한다. `auto`는 네이티브를 우선 사용하되 운영 정책에 따라 fallback을 허용할 수 있다. 정확한 테스트와 운영 장애 감지에는 `native`를 사용한다.

## 생성 경로

- `engine_override=openscad`: 치수 계약이 있는 SCAD, STL, GLB, 렌더 이미지, 조립 manifest를 생성한다.
- `engine_override=blender`: 구조 대상은 OpenSCAD로 기초 형상을 만든 뒤 Blender를 후처리로 강제한다. PBR 재질, bevel, GLB, PNG, `.blend`, USD, 재질 manifest를 생성한다.
- OpenSCAD STL의 mm 단위는 GLB로 내보낼 때 m로 변환한다.
- Blender GLB는 제품 mesh만 내보내며, 렌더용 바닥면이 제품 치수나 다운로드 모델에 섞이지 않는다.

## 95% 이상 수용 기준

95%는 임의의 프롬프트가 완성품 CAD와 95% 동일하다는 의미가 아니다. 자동화된 산업용 수용 테스트에서 다음 항목을 모두 만족한 케이스 비율을 뜻한다.

1. 요청한 네이티브 provider가 실제로 사용됨
2. 축별 치수 오차가 OpenSCAD 1%, Blender 1.5% 이내
3. 비정상 정점이 없고 face와 양의 volume이 존재함
4. OpenSCAD mesh가 watertight임
5. 경로별 필수 산출물이 모두 존재함
6. Blender PBR 재질, 1280x860 렌더, `.blend`, USD가 존재함
7. 렌더용 바닥면이 납품 GLB에 포함되지 않음

2026-07-20 네이티브 벤치마크 결과:

- 총 25건 중 25건 통과: **100.0%**
- OpenSCAD 20건, Blender 5건
- 최대 치수 오차: **0.0006%**
- OpenSCAD 평균: **1.951초**
- Blender 평균: **12.901초**

```powershell
& ".\.venv\Scripts\python.exe" ".\전체 풀스택\scripts\benchmark-native-cad.py"
```

결과는 `전체 풀스택/storage/benchmarks/native-cad/latest.md` 및 `latest.json`에 기록된다.

## 실제 API 연결 검증

로컬 스택이 실행 중일 때 다음 스모크 테스트는 PHP 프런트, Django API, Python Worker, OpenSCAD, Blender, GLB 다운로드를 관통한다.

```powershell
powershell -ExecutionPolicy Bypass -File ".\전체 풀스택\scripts\smoke-native-cad.ps1"
```

2026-07-20 실측 결과는 OpenSCAD 1.842초, Blender 14.713초, 치수 오차 0%, 두 경로 모두 `validated`였다.

## 사용 한계

- 이 검증은 치수 계약과 자산 품질에 대한 자동 검증이다. 제조 승인, 공차, 재료 강도, 체결, 가공성, 조립성, 안전 인증을 대체하지 않는다.
- 상세 기계 기구학과 복잡한 자유곡면은 사용자 검토 및 후속 CAD 설계가 필요하다.
- 새 템플릿이나 카테고리를 추가할 때는 벤치마크 케이스를 함께 추가해 95% 기준을 재검증한다.

## 공식 참고 문서

- Blender 다운로드: https://www.blender.org/download/
- Blender 설치 문서: https://docs.blender.org/manual/en/latest/getting_started/installing/index.html
- Blender glTF 내보내기: https://docs.blender.org/manual/en/latest/addons/import_export/scene_gltf2.html
- OpenSCAD 다운로드: https://openscad.org/downloads.html
- OpenSCAD 문서: https://openscad.org/documentation.html
