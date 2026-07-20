# NVIDIA NeMo Agent Toolkit Layer

`gateway.py`는 DRF가 호출하는 안정적 HTTP 경계임. 기본 `AGENT_RUNTIME=fallback`에서는 동일 계약으로 Python Worker를 직접 호출함.

실제 NAT 프로파일에서는 `pip install -e .` 후 아래와 같이 실행함.

```bash
nat serve --config_file configs/xconcep_workflow.yml
```

NAT는 오케스트레이션·도구 호출·관측·평가 계층이며, DRF의 Job/결제/권한/MySQL 역할을 대체하지 않음.
