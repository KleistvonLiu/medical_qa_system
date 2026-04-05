from __future__ import annotations

import os
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import torch
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from transformers import AutoModelForCausalLM, AutoTokenizer


DEFAULT_MODEL_ID = "Qwen/Qwen2.5-0.5B-Instruct"
DEFAULT_PORT = 8000


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatCompletionRequest(BaseModel):
    model: str | None = None
    messages: list[ChatMessage]
    max_tokens: int = Field(default=256, ge=1, le=2048)
    temperature: float = Field(default=0.2, ge=0.0, le=2.0)
    stream: bool = False
    chat_template_kwargs: dict[str, Any] | None = None


class LocalModelRuntime:
    def __init__(self) -> None:
        self.model_id = os.getenv("LOCAL_LLM_MODEL_ID", DEFAULT_MODEL_ID)
        self.served_model_name = os.getenv("LOCAL_LLM_SERVED_NAME", "qwen-local")
        self.cache_dir = os.getenv("HF_HOME", "/tmp/local-llm-hf")
        self.tokenizer = None
        self.model = None
        self.device = "cpu"
        self.loaded_at: float | None = None
        self.local_files_only = Path(self.model_id).exists()

    def load(self) -> None:
        if self.model is not None and self.tokenizer is not None:
            return

        torch.set_num_threads(
            int(os.getenv("LOCAL_LLM_NUM_THREADS", str(max(1, (os.cpu_count() or 4) // 2))))
        )
        self.tokenizer = AutoTokenizer.from_pretrained(
            self.model_id,
            cache_dir=self.cache_dir,
            local_files_only=self.local_files_only,
            trust_remote_code=False,
        )
        self.model = AutoModelForCausalLM.from_pretrained(
            self.model_id,
            cache_dir=self.cache_dir,
            local_files_only=self.local_files_only,
            trust_remote_code=False,
            dtype="auto",
        )
        self.model.eval()
        self.loaded_at = time.time()

    def generate(self, messages: list[ChatMessage], max_tokens: int, temperature: float) -> str:
        self.load()
        assert self.model is not None
        assert self.tokenizer is not None

        prompt = self.tokenizer.apply_chat_template(
            [message.model_dump() for message in messages],
            tokenize=False,
            add_generation_prompt=True,
        )
        inputs = self.tokenizer(prompt, return_tensors="pt")
        input_ids = inputs["input_ids"]
        attention_mask = inputs.get("attention_mask")

        generation_kwargs: dict[str, Any] = {
            "input_ids": input_ids,
            "attention_mask": attention_mask,
            "max_new_tokens": max_tokens,
            "pad_token_id": self.tokenizer.eos_token_id,
        }
        if temperature > 0:
            generation_kwargs["do_sample"] = True
            generation_kwargs["temperature"] = temperature
            generation_kwargs["top_p"] = 0.9
        else:
            generation_kwargs["do_sample"] = False

        with torch.no_grad():
            outputs = self.model.generate(**generation_kwargs)

        generated = outputs[0][input_ids.shape[-1] :]
        text = self.tokenizer.decode(generated, skip_special_tokens=True).strip()
        return text or "I could not generate a response."


runtime = LocalModelRuntime()


@asynccontextmanager
async def lifespan(app: FastAPI):
    runtime.load()
    yield


app = FastAPI(title="Local LLM Server", lifespan=lifespan)


@app.get("/health")
async def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "model_id": runtime.model_id,
        "served_model_name": runtime.served_model_name,
        "loaded": runtime.model is not None,
        "loaded_at": runtime.loaded_at,
    }


@app.get("/v1/models")
async def list_models() -> dict[str, Any]:
    return {
        "object": "list",
        "data": [
            {
                "id": runtime.served_model_name,
                "object": "model",
                "owned_by": "local",
            }
        ],
    }


@app.post("/v1/chat/completions")
async def chat_completions(payload: ChatCompletionRequest) -> dict[str, Any]:
    if payload.stream:
        raise HTTPException(status_code=400, detail="Streaming is not implemented in this local server.")
    if not payload.messages:
        raise HTTPException(status_code=400, detail="messages must not be empty")

    answer = runtime.generate(
        messages=payload.messages,
        max_tokens=payload.max_tokens,
        temperature=payload.temperature,
    )
    created = int(time.time())
    completion_id = f"chatcmpl-{uuid.uuid4().hex}"
    prompt_tokens = 0
    completion_tokens = 0
    if runtime.tokenizer is not None:
        prompt_tokens = len(
            runtime.tokenizer.apply_chat_template(
                [message.model_dump() for message in payload.messages],
                tokenize=True,
                add_generation_prompt=True,
            )
        )
        completion_tokens = len(runtime.tokenizer.encode(answer))

    return {
        "id": completion_id,
        "object": "chat.completion",
        "created": created,
        "model": payload.model or runtime.served_model_name,
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": answer,
                },
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
        },
    }


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("LOCAL_LLM_PORT", str(DEFAULT_PORT)))
    uvicorn.run("server:app", host="127.0.0.1", port=port, reload=False)
