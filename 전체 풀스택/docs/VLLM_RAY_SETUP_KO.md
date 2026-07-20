# Gemma 4 · vLLM · Ray 분산 배포 매뉴얼

## 전제

- 모든 노드에서 동일한 모델 디렉터리 경로를 사용함.
- 노드 간 GPU 통신 포트와 Ray 포트가 열려 있어야 함.
- NVIDIA Driver, CUDA, NCCL 버전 호환이 필요함.
- 사용자가 지정한 Gemma 4 64B는 커스텀 로컬 체크포인트로 취급함.

## 1. 설치

각 노드에서 실행함.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r infra/vllm-ray/requirements.txt
```

## 2. Ray Head

```bash
export RAY_NODE_IP=192.168.0.10
export RAY_PORT=6379
./infra/vllm-ray/ray-head.sh
```

## 3. Ray Worker

각 Worker 노드에서 실행함.

```bash
export RAY_HEAD_IP=192.168.0.10
export RAY_NODE_IP=192.168.0.11
export RAY_PORT=6379
./infra/vllm-ray/ray-worker.sh
```

## 4. vLLM 서버

Ray Head 노드의 별도 셸에서 실행함.

```bash
export GEMMA_MODEL_PATH=/models/gemma-4-64b
export GEMMA_SERVED_MODEL_NAME=gemma-4-64b-local
export VLLM_TP_SIZE=4
export VLLM_PP_SIZE=2
export VLLM_MAX_MODEL_LEN=32768
./infra/vllm-ray/serve-gemma.sh
```

`TP × PP`는 모델을 분할할 총 GPU 수와 일치하도록 설정함.

## 5. 확인

```bash
curl http://192.168.0.10:8000/v1/models
```

```bash
curl http://192.168.0.10:8000/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{
    "model":"gemma-4-64b-local",
    "messages":[{"role":"user","content":"JSON으로 응답함"}],
    "max_tokens":128
  }'
```

## 6. 애플리케이션 연결

```env
LLM_MODE=vllm
VLLM_BASE_URL=http://192.168.0.10:8000/v1
VLLM_API_KEY=local-not-required
GEMMA_MODEL_NAME=gemma-4-64b-local
```

## 7. 주요 리스크

- 커스텀 모델 Config에 vLLM TP/PP Plan이 없으면 분산 실행이 실패할 수 있음.
- 멀티모달 이미지 입력 지원 여부는 실제 체크포인트와 vLLM 지원 모델 목록을 확인해야 함.
- 멀티노드는 Ray IP와 `VLLM_HOST_IP`가 잘못 설정되면 NCCL 통신이 실패함.
- 단일 모델 지연시간이 중요하면 Data Parallel보다 TP/PP 조합을 우선 검토함.
