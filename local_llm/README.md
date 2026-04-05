# Local LLM Server

This directory contains a minimal OpenAI-compatible local chat server intended to mimic the runtime contract that `corp_chatbot` expects when `CHATBOT_PROVIDER=vllm`.

## Endpoints

- `GET /health`
- `GET /v1/models`
- `POST /v1/chat/completions`

## Default Model

- `Qwen/Qwen2.5-0.5B-Instruct`

This default is chosen because the current machine does not have a working NVIDIA driver or `vllm`, so a CPU-friendly smaller model is the most reliable way to start a local LLM service.

## Run

```bash
uv sync --project local_llm
HF_HOME=/tmp/local-llm-hf \
LOCAL_LLM_MODEL_ID=Qwen/Qwen2.5-0.5B-Instruct \
LOCAL_LLM_SERVED_NAME=qwen-local \
uv run --project local_llm python local_llm/server.py
```

## corp_chatbot Example Env

```env
CHATBOT_PROVIDER=vllm
EMBEDDING_PROVIDER=offline
VLLM_BASE_URL=http://127.0.0.1:8000/v1
VLLM_CHAT_MODEL=qwen-local
VLLM_ENABLE_THINKING=false
VLLM_STRIP_THINK_OUTPUT=true
```
