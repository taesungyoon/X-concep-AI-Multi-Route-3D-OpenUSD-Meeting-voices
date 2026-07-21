# Hunyuan3D 2.1 로컬 설치·연결

> 현재 채택하지 않는 레거시 문서임. Hunyuan3D 2.0/2.1 라이선스의 허용 지역에 대한민국이 포함되지 않아 이 프로젝트의 기본 또는 선택 운영 엔진으로 사용하지 않음. 실제 구성은 `TRIPOSR_SETUP_KO.md`를 따름.

## 1. 설치

```bash
./infra/hunyuan3d/install.sh
```

기본 설치 위치는 `$HOME/Hunyuan3D-2.1`임.

## 2. API 서버 실행

```bash
export HUNYUAN_PORT=8081
./infra/hunyuan3d/run-api.sh
```

## 3. 애플리케이션 설정

```env
HUNYUAN_MODE=local_api
HUNYUAN_API_URL=http://HUNYUAN_SERVER_IP:8081
HUNYUAN_TIMEOUT_SECONDS=1800
HUNYUAN_TEXTURE=true
```

## 4. 통신 계약

Python Worker는 다음 요청을 전송함.

```json
{
  "image": "BASE64_IMAGE",
  "texture": true
}
```

다음 응답 유형을 지원함.

- GLB Binary 응답
- `glb_base64`, `model_base64`, `file_base64`
- `glb_url`, `file_url`, `download_url`
- 공유 볼륨의 `file_path`

## 5. GPU 운영

- Hunyuan3D는 vLLM 서버와 GPU를 공유하지 않는 별도 Worker를 권장함.
- 생성 Queue와 동시 작업 수를 GPU 메모리 기준으로 제한해야 함.
- Preview PNG까지 필요한 경우 Blender Headless를 별도 CPU/GPU Worker로 분리할 수 있음.

## 6. 라이선스 확인

Hunyuan3D 2.1은 일반적인 Apache/MIT 라이선스가 아니라 Tencent Community License 조건이 포함됨. 상업 서비스, 배포 지역, 제3자 제공, 표시 의무를 실제 도입 전에 법무 검토해야 함.
