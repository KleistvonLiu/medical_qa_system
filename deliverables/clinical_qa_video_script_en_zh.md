# Clinical QA MVP Video Script

Use this as speaker notes for a `25-30 minute` walkthrough of the system that is actually implemented in this repo. The English sections are what you can say in the interview. The Chinese lines are memory cues.

## 0. Title And Framing

- Suggested title: `Building a Clinical QA MVP Grounded in ClinicalTrials.gov and PubMed`
- Suggested format: `8-10 slides`
- Positioning: `implemented MVP walkthrough`, not just a hypothetical architecture

### English

In this walkthrough, I am going to explain a clinical question answering MVP that I actually implemented locally. The system takes a natural-language clinical question, retrieves evidence from ClinicalTrials.gov and PubMed, synthesizes a grounded answer with an LLM, validates citations, and returns a structured response that users can inspect.

This is not a diagnosis engine and it is not meant to replace a clinician. I frame it as an evidence-grounded retrieval and synthesis system. The model is not the source of truth. ClinicalTrials.gov and PubMed are the source of truth, and the model's job is to organize retrieved evidence into a useful answer.

### 中文提示

开场先说明这是“已经实现的 MVP”，不是纯白板设计。强调 source of truth 是 ClinicalTrials.gov 和 PubMed，不是模型。

## 1. What The Current Product Actually Does

Time: `2-3 minutes`

### English

The current product is a single-page web app with a FastAPI backend and a React frontend.

The user can ask one clinical question at a time. The backend then:

1. checks the local cache,
2. extracts question intent,
3. decides whether to query ClinicalTrials.gov, PubMed, or both,
4. retrieves live evidence,
5. normalizes source records into snippets,
6. reranks those snippets,
7. asks an LLM for a structured answer,
8. validates citations,
9. and returns the answer together with limitations, citations, debug metadata, and a full pipeline trace.

On the frontend, the answer is always rendered in four blocks:

- direct answer,
- why this answer,
- limitations,
- and grouped citations.

There is also a source drawer and a pipeline trace drawer, so the system is highly inspectable.

### 中文提示

先给面试官一个 concrete mental model。后端 9 步，前端 4 个 answer blocks，加 source drawer 和 trace drawer。

## 2. System Boundaries And MVP Choices

Time: `2 minutes`

### English

This implementation is deliberately conservative.

It is single-turn, not multi-turn chat.

It uses live retrieval plus SQLite caching, not a full offline ingestion pipeline yet.

It supports both OpenAI and a local vLLM server through configuration, because I wanted the same backend to run either against hosted models or against a local GPU model.

And it is abstract-grounded on the PubMed side, because the standard PubMed path gives reliable access to metadata and abstracts, but not guaranteed full text.

So if I summarize the MVP philosophy in one sentence, it is:

simple pipeline, source-aware retrieval, bounded evidence, inspectable output, and conservative fallback behavior.

### 中文提示

强调这是有意做小做稳的 MVP。single-turn，live retrieval + cache，provider-neutral，PubMed abstract-grounded。

## 3. High-Level Architecture

Time: `3 minutes`

### English

At a high level, the request path is:

Frontend -> `POST /api/qa` -> `QAService` -> cache lookup -> intent analysis -> source-specific retrieval -> snippet reranking -> structured answer generation -> citation validation -> final response.

The major backend modules are:

- `main.py`
  HTTP entrypoints and dependency wiring.
- `qa.py`
  The orchestration layer for the full question answering pipeline.
- `clinicaltrials.py`
  ClinicalTrials.gov retrieval, status-aware search planning, and trial normalization.
- `pubmed.py`
  PubMed `esearch -> esummary -> efetch` retrieval and abstract parsing.
- `rerank.py`
  Hybrid scoring plus source diversity control.
- `llm_service.py`
  Provider-neutral structured generation and optional embeddings.
- `cache.py`
  Query cache, source cache, embedding cache, and request trace logging.

The frontend is thin by design. It submits the question, renders the structured response, and exposes inspectability through citation drawers and the pipeline trace UI.

### 中文提示

把代码模块直接讲出来。核心 orchestrator 是 `qa.py`，前端故意做薄。

## 4. The Real Backend Request Flow

Time: `5 minutes`

### English

Now I will walk through what really happens when a question hits the backend.

First, the request enters `POST /api/qa`.

The backend creates a request ID, cleans expired cache rows, computes a cache key from the normalized question, filters, `max_sources`, and runtime provider context, and then checks whether the exact request already exists in query cache.

If there is a cache hit, the backend returns the cached response immediately, but it still updates the trace summary so the UI shows that the answer came from cache.

If there is no cache hit, the backend calls the intent layer. This produces a `QuestionIntent` object with fields like:

- route: `trials`, `pubmed`, or `blended`
- focus
- extracted condition terms
- extracted intervention terms
- extracted outcome terms
- merged filters

Then the backend runs source-specific retrieval.

ClinicalTrials.gov uses `/api/v2/studies` and tries structured parameters such as `query.cond`, `query.intr`, and a safer `query.term` fallback. The search planner is also status-aware. If the question asks for recruiting trials, the backend applies recruiting-oriented filtering instead of just retrieving the first few records and filtering afterward.

PubMed uses `esearch` to get candidate PMIDs, then `esummary` and `efetch` to get metadata and abstract text. The backend constructs a PubMed search term from condition, intervention, population, and outcome cues, and it respects NCBI rate limits.

After retrieval, each source is normalized into a shared internal record, and each record is split into evidence snippets.

For trials, snippets come from sections like status, summary, eligibility, and outcomes.

For PubMed, snippets come from title, metadata, and abstract sentence chunks.

Those snippets then go into reranking.

### 中文提示

这里要讲真实 request lifecycle：cache key，intent，ClinicalTrials 查询参数，PubMed 三段式调用，最后统一成 snippets。

## 5. Retrieval Strategy By Source

Time: `4 minutes`

### English

The key point in this system is that retrieval is source-aware.

For ClinicalTrials.gov, I am not treating it like generic full-text search. I preserve trial-specific semantics such as:

- recruiting status,
- phase,
- condition,
- intervention,
- eligibility,
- and primary outcomes.

That matters because a question like "Are there any recruiting clinical trials for pembrolizumab in metastatic triple-negative breast cancer?" should be routed differently from a literature question. In the current implementation, that question becomes a trials route, and the backend builds a status-aware trial query instead of sending the raw sentence as a loose search string.

For PubMed, the retrieval logic is different. I build a PubMed-style query from extracted terms and outcome intent. For example, a question about semaglutide safety in obesity becomes a PubMed query built around obesity, semaglutide, and safety terms, followed by abstract retrieval and normalization.

For blended questions, the system hits both branches independently, then merges evidence later instead of mixing the source semantics too early.

### 中文提示

核心是 source-aware retrieval。Q1 是 trial registry search，Q2 是 PubMed evidence search，Q3 是双路并行后再 merge。

## 6. Reranking And Evidence Assembly

Time: `3 minutes`

### English

Once I have candidate snippets, I run a bounded hybrid reranker.

The score combines:

- source rank from the upstream retrieval,
- keyword overlap with the original question,
- and embedding similarity when embeddings are enabled.

On my local vLLM setup, embeddings are usually disabled, so the reranker automatically renormalizes to rely on source rank plus lexical overlap.

I also added a diversity constraint so one single paper or one single trial does not dominate the entire top-k list. That matters in practice because otherwise multiple snippets from the same source can crowd out useful alternative evidence.

The result is a small evidence set that is easier for the model to handle and easier for humans to inspect.

### 中文提示

讲清 hybrid rerank 不是复杂向量库。默认本地模式 embeddings 关掉，但还能工作。还做了 source diversity。

## 7. LLM Integration And Citation Grounding

Time: `4 minutes`

### English

The LLM is used twice.

First, it extracts intent into a structured schema.

Second, it generates a structured answer draft with:

- `direct_answer`
- `why_this_answer`
- `limitations`
- `citation_ids`

The backend uses a provider-neutral path based on OpenAI-compatible chat completions with JSON schema output. That lets the same code work with OpenAI or with a local vLLM server.

There are a few practical safeguards here.

One, if vLLM returns residual reasoning text, the backend strips it before parsing JSON.

Two, if the model returns citation identifiers in the wrong format, for example a `PMID` instead of the internal `snippet_id`, the backend now normalizes that identifier to the matching snippet when possible.

Three, if structured generation fails or citations are unsupported after retries, the system falls back to a conservative extractive answer instead of returning a broken answer.

So the model is not trusted blindly. It is constrained, normalized, validated, and only then turned into the final response.

### 中文提示

这是最重要的一页之一。LLM 用两次。结构化输出，provider-neutral，thinking strip，citation normalize，失败就 extractive fallback。

## 8. Frontend And Debuggability

Time: `2-3 minutes`

### English

On the frontend, the answer UI is intentionally simple but transparent.

The main page shows:

- the direct answer,
- supporting bullets,
- limitations,
- grouped citations by source type.

If the user clicks a citation, the frontend opens a source drawer and fetches cached source metadata and available snippets from `GET /api/sources/{source_type}/{source_id}`.

If the user clicks "View pipeline trace", the frontend opens a trace drawer that shows all eight stages:

- cache,
- intent,
- ClinicalTrials retrieval,
- PubMed retrieval,
- rerank,
- answer generation,
- citation validation,
- final response.

This is important because it turns the system from a black box into a debuggable product. If an answer is weak, I can inspect whether the problem came from routing, retrieval, reranking, or generation.

### 中文提示

前端重点不是炫 UI，而是 inspectability。source drawer 和 trace drawer 是可信度和 debug 的关键。

## 9. Three Real Example Questions

Time: `4 minutes`

### English

I tested the system with three representative questions.

First:

`Are there any recruiting clinical trials for pembrolizumab in metastatic triple-negative breast cancer?`

This routes to `trials`. The backend now correctly retrieves recruiting trials and cites `NCT` records such as `NCT06246968`, instead of incorrectly saying no recruiting trials exist.

Second:

`What does the published literature say about the safety of semaglutide in adults with obesity?`

This routes to `pubmed`. The backend builds a PubMed query around obesity, semaglutide, and safety, retrieves PubMed records like `PMID 36216945`, and returns a grounded answer instead of degrading because of citation formatting issues.

Third:

`What trials are ongoing for CAR-T therapy in multiple myeloma and what published evidence already exists?`

This routes to `blended`. The system retrieves both ongoing trial records and published literature, then produces one answer that separates the trial side from the literature side.

This third example is also useful because it shows a real remaining tradeoff. The retrieval layer now finds multiple relevant trials, but the final summary can still under-enumerate the full trial landscape. That is no longer a retrieval failure. It is a summarization and evidence-window tradeoff.

### 中文提示

把这三个真实问题当成 demo。顺便说明我们不仅修了 bug，也看到了当前剩余的边界。

## 10. Tradeoffs And What I Would Improve Next

Time: `3 minutes`

### English

The current MVP makes a few deliberate tradeoffs.

First, it uses live retrieval plus TTL caching instead of full pre-ingestion. That keeps implementation simpler, but a production version should add a stronger offline indexing layer for latency, recall, and observability.

Second, it uses bounded reranking instead of a full vector database. That is the right MVP choice, especially when local embeddings may be disabled, but it limits large-scale recall and semantic search quality.

Third, PubMed is abstract-grounded. That is honest and workable for an MVP, but a production system should differentiate more clearly between abstract-only evidence and full-text evidence.

Fourth, blended answers are still the hardest case. If I were extending this system, I would invest next in:

- stronger intent extraction for multi-part questions,
- better evidence budgeting per source,
- and more explicit answer planning for "list ongoing trials plus summarize literature" style requests.

### 中文提示

tradeoff 要讲真实，不要假装系统已经 production-ready。下一步重点是 pre-ingestion、better retrieval budget、blended answer planning。

## 11. Closing

Time: `1 minute`

### English

So to summarize, this MVP already demonstrates the architecture I care about in a clinical QA setting:

- source-aware retrieval,
- conservative grounded synthesis,
- citation validation,
- provider flexibility,
- and full pipeline inspectability.

If I were taking it from MVP to production, I would focus next on stronger indexing, deeper evaluation, and better handling of multi-source synthesis. But even in its current form, the system already shows the core product principle I care about most:

the answer should be faithful to retrieved evidence, and the user should be able to inspect how that answer was produced.

### 中文提示

收尾就强调 faithful to evidence 和 inspectability。这是整套系统最重要的价值判断。
