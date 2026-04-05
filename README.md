# Clinical QA MVP

This repo now contains a working local MVP for a clinical question answering website.

The app accepts a single clinical question, retrieves live evidence from `ClinicalTrials.gov` and `PubMed`, caches normalized source data in SQLite, can use either OpenAI or a local `vLLM` server for grounded synthesis, and always returns inspectable citations.

The original interview-prep materials are still available under [`deliverables/`](/home/kleist/Documents/Code/medical_QA_system/deliverables).

## Architecture

- `backend/`
  FastAPI app with live retrieval, SQLite cache, hybrid reranking, grounded answer synthesis, and source detail endpoints.
- `frontend/`
  React + TypeScript + Vite single-page app with example questions, filters, grouped citations, debug panel, and a source drawer.
- `deliverables/`
  The interview script, slide outline, and follow-up Q&A pack.

## Product Behavior

- `POST /api/qa`
  Accepts `question`, `filters`, and `max_sources`.
- `GET /api/sources/{source_type}/{source_id}`
  Returns cached normalized source metadata and snippets.
- `GET /api/health`
  Returns backend status, SQLite availability, provider readiness, and cache cleanup timestamp.

The system is conservative by design:

- If the configured chat provider is unavailable, it falls back to extractive answers instead of failing.
- If citation validation fails twice, it falls back to an extractive answer.
- PubMed support is abstract-grounded unless richer source text is available.

## Backend Setup

Requirements:

- Python `3.10+`
- `uv`

Install and run:

```bash
uv sync --project backend
uv run --project backend uvicorn app.main:app --reload --host 127.0.0.1 --port 8001
```

Backend runs at `http://127.0.0.1:8001`.

Environment variables:

- Provider selection:
  - `CHAT_PROVIDER=openai|vllm`
  - `EMBED_PROVIDER=openai|vllm|none`
- OpenAI:
  - `OPENAI_API_KEY`
  - `OPENAI_BASE_URL`
  - `OPENAI_CHAT_MODEL`
  - `OPENAI_MODEL` as a backward-compatible alias
  - `OPENAI_EMBED_MODEL`
- vLLM:
  - `VLLM_BASE_URL`
  - `VLLM_API_KEY`
  - `VLLM_CHAT_MODEL`
  - `VLLM_EMBED_MODEL`
  - `VLLM_ENABLE_THINKING`
  - `VLLM_STRIP_THINK_OUTPUT`
- Shared:
  - `CHAT_MAX_COMPLETION_TOKENS`
  - `CHAT_TEMPERATURE`
  - `NCBI_TOOL_NAME`
  - `NCBI_TOOL_EMAIL`
  - `NCBI_API_KEY`
  - `SQLITE_PATH`

Copy [`backend/.env.example`](/home/kleist/Documents/Code/medical_QA_system/backend/.env.example) to `backend/.env` if you want a local env file.

Recommended local `vLLM` mode for this machine:

```env
CHAT_PROVIDER=vllm
EMBED_PROVIDER=none
VLLM_BASE_URL=http://127.0.0.1:8000/v1
VLLM_CHAT_MODEL=qwen35
VLLM_ENABLE_THINKING=false
VLLM_STRIP_THINK_OUTPUT=true
```

## Frontend Setup

Requirements:

- Node `22+`
- `npm`

Install and run:

```bash
cd frontend
npm install
npm run dev
```

Frontend runs at `http://127.0.0.1:5173` and proxies `/api` to the backend at `http://127.0.0.1:8001` by default.

If you need a custom backend origin, set:

```bash
VITE_API_BASE_URL=http://127.0.0.1:8001
```

## Tests

Backend tests cover:

- ClinicalTrials query building and normalization
- PubMed query building and abstract parsing
- Hybrid reranking
- Citation validation
- Provider config resolution
- vLLM thinking cleanup and structured-output compatibility
- Five integration flows:
  - trials-first
  - pubmed-first
  - blended
  - no results
  - OpenAI failure fallback

Run:

```bash
uv run --project backend pytest
```

## Demo Checklist

1. Start `vLLM` on `127.0.0.1:8000` if you are using local inference.
2. Start the backend on `127.0.0.1:8001`.
3. Start the frontend.
4. Ask a recruiting-trial question and confirm `NCT` citations appear.
5. Ask a literature question and confirm `PMID` citations appear.
6. Open a citation card and inspect the cached source drawer.
7. Switch providers in `backend/.env` and confirm `/api/health` reports the expected `chat_provider` and `embedding_provider`.

## Official References

- ClinicalTrials.gov API: <https://clinicaltrials.gov/data-api/api>
- ClinicalTrials.gov search areas: <https://clinicaltrials.gov/data-api/about-api/search-areas>
- NCBI developer APIs: <https://www.ncbi.nlm.nih.gov/home/develop/api/>
- NCBI E-utilities usage guidance: <https://eutilities.github.io/site/API_Key/usageandkey/>
- OpenAI chat response formatting: <https://platform.openai.com/docs/api-reference/chat/response-formatting>
- vLLM OpenAI-compatible server: <https://docs.vllm.ai/en/latest/serving/openai_compatible_server/>
- vLLM structured outputs: <https://docs.vllm.ai/en/latest/features/structured_outputs/>
