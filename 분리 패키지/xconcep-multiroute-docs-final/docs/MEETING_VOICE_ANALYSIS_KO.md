# 회의 음성 분석 기능 매뉴얼

## 1. 사용자 흐름

1. 상단에서 `회의 음성 분석` 모드를 선택함
2. 생성 유형을 설비·모듈·부품 중 선택함
3. `녹음 시작`을 누르고 브라우저 마이크 권한을 허용함
4. 녹음 중 15초마다 오디오 Chunk가 서버로 전송됨
5. Transcript 패널에서 전사 결과를 확인함
6. 오인식 문장은 수동 Transcript 영역에서 수정함
7. `회의 내용 분석`을 누름
8. Gemma가 아래 항목을 구조화함
   - 회의 요약
   - 확정 요구사항
   - 요청 변경사항
   - 주요 치수
   - 구성 부품
   - 동작 원리
   - 안전 요구사항
   - 미확정 항목
   - 후속 조치
   - 2D 생성 프롬프트
9. `현재 내용으로 2D 생성`을 눌러 기존 2D 비교 단계로 이동함
10. 회의가 계속되면 추가 Transcript를 분석하고 Patch·Revision을 생성함

## 2. STT 모드

### Mock

```env
SPEECH_MODE=mock
```

화면·API 연동 확인용임.

### faster-whisper 로컬

```env
SPEECH_MODE=faster_whisper
INSTALL_SPEECH=true
WHISPER_MODEL=large-v3-turbo
WHISPER_DEVICE=cuda
WHISPER_COMPUTE_TYPE=float16
```

설치 의존성은 `python-worker/requirements-speech.txt`에 정의함.

### NVIDIA Speech NIM

```env
SPEECH_MODE=nvidia_nim
NVIDIA_ASR_URL=http://ASR-NIM:9000
NVIDIA_ASR_API_KEY=
```

현재 `speech_client.py`의 NIM Adapter는 공식 HTTP REST `/v1/audio/transcriptions` 계약을 기준으로 하며 multipart 필드 `file`을 사용함. 브라우저 WebM 청크는 Worker에서 FFmpeg를 이용해 16kHz Mono WAV로 변환한 뒤 전송함. 지속 스트리밍·부분 전사·화자 분리가 필요한 경우 NVIDIA NIM WebSocket 또는 gRPC Streaming Client를 별도 적용해야 함.

## 3. 화자 분리

기본값은 단순 교차 Speaker Label 방식임.

```env
DIARIZATION_MODE=none
```

실제 운영에서는 아래 중 하나로 대체해야 함.

- NVIDIA ASR/Riva Streaming Diarization
- pyannote 기반 로컬 Diarization
- 회의 장비 채널별 독립 마이크

화자 분리 오류는 요구사항 책임 주체를 잘못 지정할 수 있으므로 최종 승인 전에 Transcript 확인이 필요함.

## 4. Gemma 분석 계약

Gemma 응답은 JSON 객체만 허용함.

```json
{
  "summary": "회의 요약",
  "confirmed_requirements": [],
  "requested_changes": [],
  "dimensions": {
    "width_mm": null,
    "depth_mm": null,
    "height_mm": null
  },
  "components": [],
  "operating_principle": "",
  "safety_requirements": [],
  "unresolved_items": [],
  "action_items": [],
  "generation_prompt": "",
  "revision_note": "",
  "usd_metadata": {}
}
```

불확실한 발언은 `confirmed_requirements`로 승격하지 않도록 System Prompt에 제한함.

## 5. 중간 생성과 Revision

회의 중 `현재 내용으로 2D 생성`을 누른 시점이 생성 기준점임. 이후 회의에서 치수·구동부·안전 요구사항이 변경되면 `/meeting/patch`가 다음 Revision을 생성함.

```text
Rev.1 최초 회의 분석
Rev.2 폭 800 → 900 mm
Rev.3 실린더 → 서보모터
Rev.4 안전커버·브래킷 반영
```

Revision 정보는 프로젝트 JSON과 OpenUSD Revision Layer에 함께 저장함.

## 6. 오디오 보안

- 회의 오디오는 `storage/projects/{project_id}/meeting/audio/`에 저장함
- 운영 환경에서는 프로젝트별 접근 권한과 보존기간을 설정해야 함
- 음성·Transcript는 민감한 고객 설계정보가 포함될 수 있으므로 공개 Web Root와 분리된 Object Storage 사용을 권장함
- HTTPS와 마이크 권한 정책을 적용해야 함
