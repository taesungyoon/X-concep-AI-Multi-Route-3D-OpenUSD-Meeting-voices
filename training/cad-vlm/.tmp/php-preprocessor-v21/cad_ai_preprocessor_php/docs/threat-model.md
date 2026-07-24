# 위협 모델

- 허용 확장자와 파일 시그니처를 함께 확인한다.
- 업로드 크기는 PHP 설정과 애플리케이션 양쪽에서 제한한다.
- 저장명은 난수 UUID 계열 값이며 원래 파일명은 메타데이터로만 보존한다.
- artifact 상대 경로에 `..`를 허용하지 않고 resolved 경로가 작업 루트 하위인지 확인한다.
- SQL은 Prepared Statement만 사용한다.
- UI는 사용자 입력을 `textContent`로 렌더링한다.
- CSP, `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`를 적용한다.
- 운영에서는 TLS, 상위 인증, 악성코드 검사, 디스크 할당량, 보존·파기 정책을 추가한다.
