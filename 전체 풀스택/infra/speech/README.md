# Speech Runtime

## faster-whisper

```bash
pip install -r python-worker/requirements-speech.txt
```

```env
SPEECH_MODE=faster_whisper
WHISPER_MODEL=large-v3-turbo
WHISPER_DEVICE=cuda
WHISPER_COMPUTE_TYPE=float16
```

## NVIDIA Speech NIM

NVIDIA NGC에서 운영 환경에 맞는 ASR NIM을 배포한 후 아래 값을 지정함.

```env
SPEECH_MODE=nvidia_nim
NVIDIA_ASR_URL=http://ASR_NIM:9000
```

직접 REST·gRPC·WebSocket Streaming API를 사용할 경우 `python-worker/app/speech_client.py`의 Adapter를 해당 API 계약에 맞춰 구현함.
