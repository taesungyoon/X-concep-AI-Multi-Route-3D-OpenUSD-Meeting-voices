# 내부 MySQL 인증 테스트

## 현재 기본 구성

- 프로젝트 데이터베이스: Docker Compose의 `mysql:8.4`
- 사용자 인증 데이터베이스: 같은 내부 MySQL의 Django `auth_user` 테이블
- 인증 모드: `AUTH_MODE=internal_db`
- 외부 사내 MySQL: 비활성 상태로 보존하며 추후 `corporate_db`로 전환 가능

컨테이너 시작 시 Django 마이그레이션이 내부 사용자 테이블을 만들고, `bootstrap_internal_auth` 명령이 `.env`의 테스트 사용자를 생성하거나 갱신함. 비밀번호는 로그와 API 응답에 출력하지 않음.

## .env 핵심값

```dotenv
DB_ENGINE=mysql
MYSQL_HOST=mysql
MYSQL_PORT=3306
MYSQL_DATABASE=xconcep
MYSQL_USER=xconcep
MYSQL_PASSWORD=로컬_DB_비밀번호
MYSQL_ROOT_PASSWORD=로컬_ROOT_비밀번호

AUTH_MODE=internal_db
INTERNAL_AUTH_BOOTSTRAP_ENABLED=true
INTERNAL_AUTH_USERNAME=internal_admin
INTERNAL_AUTH_PASSWORD=로컬_로그인_비밀번호
INTERNAL_AUTH_DISPLAY_NAME=내부 테스트 관리자
INTERNAL_AUTH_EMAIL=internal-admin@example.test
```

`.env`는 Git에서 제외됨. `.env.example`에는 실제 비밀번호 대신 자리표시자만 유지함.

## 실행 및 확인

```powershell
docker compose -p xconcep up -d mysql redis qdrant
docker compose -p xconcep up -d --build
```

웹 접속 후 `INTERNAL_AUTH_USERNAME`과 `INTERNAL_AUTH_PASSWORD`로 로그인함. 상태 API의 `worker.authentication`에서 다음을 확인함.

```json
{
  "mode": "internal_db",
  "required": true,
  "database_connected": true
}
```

## 외부 MySQL로 전환할 때

`AUTH_MODE=corporate_db`로 변경하고 `AUTH_DB_HOST`, 계정, 데이터베이스명, 사용자 테이블/컬럼 매핑을 입력함. 내부 계정은 삭제할 필요가 없으며 외부 모드에서는 사용되지 않음.
