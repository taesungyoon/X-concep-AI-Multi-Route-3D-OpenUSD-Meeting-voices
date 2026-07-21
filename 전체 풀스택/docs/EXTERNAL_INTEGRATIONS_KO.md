# 외부 연동 준비 및 승인 경계

## 확정 구성

- 기본 2D 생성: 로컬 ComfyUI + FLUX
- 추가 2D 생성 모드: OpenAI Image API
- 현재 사용자 인증: 내부 MySQL의 Django 사용자 테이블
- 추후 사용자 인증: 외부 사내 MySQL의 기존 사용자 테이블 조회
- 서비스 데이터베이스와 사내 인증 데이터베이스는 별도 연결로 유지함

현재 기본값은 `AUTH_MODE=internal_db`이며 내부 MySQL에서만 로그인 테스트함. 외부 사내 인증은 추후 `.env`를 `AUTH_MODE=corporate_db`로 변경할 때만 활성화됨.

## 사용자가 .env에 채울 값

먼저 `.env.example`을 `.env`로 복사한 뒤 다음 값을 채움.

```dotenv
AUTH_MODE=corporate_db
AUTH_DB_ENGINE=mysql
AUTH_DB_HOST=사내_MySQL_IP_또는_DNS
AUTH_DB_PORT=3306
AUTH_DB_NAME=데이터베이스명
AUTH_DB_USER=읽기전용_계정
AUTH_DB_PASSWORD=비밀번호
AUTH_DB_SSL_CA=CA_파일_경로_또는_빈값

AUTH_DB_TABLE=사용자_테이블
AUTH_DB_ID_COLUMN=고유키_컬럼
AUTH_DB_USERNAME_COLUMN=로그인_ID_컬럼
AUTH_DB_PASSWORD_COLUMN=암호_해시_컬럼
AUTH_DB_DISPLAY_NAME_COLUMN=표시명_컬럼
AUTH_DB_EMAIL_COLUMN=이메일_컬럼
AUTH_DB_ACTIVE_COLUMN=활성여부_컬럼
AUTH_DB_PASSWORD_SCHEME=django_hash
```

인증용 DB 계정에는 대상 사용자 테이블에 대한 `SELECT` 권한만 부여하는 것을 권장함. 현재 검증기는 Django 형식의 PBKDF2/bcrypt/argon2 해시를 지원함. 사내 해시가 PHP의 원시 bcrypt, 별도 salt 컬럼, 사내 SSO 프로토콜 등 다른 형식이면 실제 연결 전에 해시 예시가 아닌 **알고리즘과 저장 형식**만 알려주면 전용 검증기를 추가할 수 있음.

OpenAI 추가 모드는 다음 값을 채우고 `OPENAI_IMAGE_MODE=openai`로 전환함. 기본 모드는 `comfyui`임.

```dotenv
OPENAI_API_KEY=
OPENAI_ORGANIZATION=
OPENAI_PROJECT=
OPENAI_IMAGE_MODEL=gpt-image-2
OPENAI_IMAGE_SIZE=1536x1024
OPENAI_IMAGE_QUALITY=medium
OPENAI_IMAGE_MAX_REQUESTS_PER_DAY=20
OPENAI_IMAGE_ESTIMATED_COST_USD=요청당_추정비용
OPENAI_IMAGE_MAX_ESTIMATED_COST_USD_PER_DAY=일일_추정비용_상한
```

키·비밀번호·원문 프롬프트는 사용량 장부나 상태 API에 기록하지 않음. OpenAI 사용량 장부에는 프롬프트 SHA-256, 모델·크기·품질, 추정 비용, 처리 결과와 요청 ID만 기록함.

## 실제 연결 전 검증

```powershell
python scripts/preflight-integrations.py --env .env.example --template
python scripts/preflight-integrations.py --env .env
```

위 명령은 설정만 검증하고 네트워크에 접속하지 않음. 실제 접속은 사용자 승인 후에만 다음 순서로 수행함.

```powershell
python scripts/preflight-integrations.py --env .env --live --confirm-external
powershell -ExecutionPolicy Bypass -File scripts/smoke-external-integrations.ps1 -ConfirmExternal
```

OpenAI로 실제 이미지를 생성하는 유료 스모크 테스트는 추가 확인 스위치가 없으면 중단됨.

```powershell
powershell -ExecutionPolicy Bypass -File scripts/smoke-external-integrations.ps1 -ConfirmExternal -ConfirmPaidImage
```

## 승인 전 중단점

내부 MySQL의 마이그레이션·계정 생성·로그인은 실제 검증을 완료함. 사용자가 외부 연결을 다시 결정하고 승인하기 전에는 사내 MySQL, OpenAI, 기타 외부 API에 접속하지 않음.
