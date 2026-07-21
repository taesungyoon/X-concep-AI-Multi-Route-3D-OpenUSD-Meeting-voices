# 제3자 구성요소 및 라이선스 확인사항

## OpenAI GPT Image API

외부 상용 API임. API 이용약관, 데이터 보존정책, 비용과 출력물 정책을 운영 전 확인해야 함.

## Gemma 계열 체크포인트

본 전달본은 `gemma-4-64b-local`이라는 사용자 제공 Served Model Name을 사용함. 모델 가중치는 포함하지 않음. 사용자가 보유한 실제 체크포인트의 Gemma License·파생 모델 조건·배포 조건을 확인해야 함.

## vLLM·Ray

오픈소스 프로젝트이나 실제 모델·CUDA·NCCL·Driver 조합의 호환성을 확인해야 함.

## TripoSR

VAST-AI-Research/TripoSR 코드와 stabilityai/TripoSR 모델은 MIT 라이선스임. 모델 가중치는 저장소에 포함하지 않고 최초 실행 시 Hugging Face에서 내려받음.

Hunyuan3D 2.0/2.1은 라이선스상 대한민국이 허용 지역에 포함되지 않아 현재 운영 스택에서 제외함.

## OpenUSD

OpenUSD 라이선스와 포함된 Python Package의 고지사항을 배포물에 유지해야 함.

## NVIDIA Omniverse·Kit·Nucleus·Speech NIM

NVIDIA 제품·SDK·Container·NGC Artifact에는 각 EULA·Enterprise License·Container License가 적용될 수 있음. 본 저장소에는 NVIDIA Runtime과 Container Image를 포함하지 않으며, Extension Source와 연동 설정만 포함함.

## faster-whisper·CTranslate2

오픈소스 라이선스와 사용하는 Whisper Model Weight의 라이선스를 확인해야 함.

## Three.js

프론트엔드 라이선스 고지를 유지해야 함.
