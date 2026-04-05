# Clinical QA 面试展示 Runbook

目标：用 `PPT + 现场看页面/代码` 的方式，在 `30 分钟内` 回答下面四类问题：

- How you would architect the backend
- How you'd structure queries against ClinicalTrials.gov and PubMed
- Your approach to surfacing accurate, cited answers
- Any tradeoffs or design decisions you'd make

这个 repo 已经有一个 working MVP，所以最好的讲法不是“假设我要怎么设计”，而是：

`我先给出架构思路 -> 再用当前代码证明我会把这些思路落到什么程度 -> 最后主动讲 tradeoff。`

---

## 总体建议

### 你这场展示最好的主线

不要按“模块介绍”讲。

按下面这条主线讲更强：

`一个临床问题进来之后，系统如何决定去哪里找证据，如何把不同来源的证据结构化，如何让 LLM 只做受约束的 synthesis，而不是乱答。`

这样正好覆盖面试官关心的四点。

### 你要刻意强调的定位

- 这是一个 `evidence-grounded QA system`，不是 diagnosis engine。
- `ClinicalTrials.gov` 和 `PubMed` 是 source of truth，模型不是。
- 你的设计重点不是“模型多强”，而是：
  - source-aware retrieval
  - bounded evidence
  - citation validation
  - inspectability

### 30 分钟推荐分配

- `3 min` 开场和 framing
- `6 min` backend architecture
- `7 min` query design: ClinicalTrials + PubMed
- `7 min` accurate cited answers
- `4 min` tradeoffs and design decisions
- `3 min` buffer / Q&A

---

## Slide 1

### PPT 内容

标题：`Clinical QA MVP: Grounded Answers over ClinicalTrials.gov and PubMed`

页面只放三件事：

- 一句话定义：
  - `Single-turn clinical QA system with live retrieval, grounded synthesis, and inspectable citations`
- 一句话边界：
  - `Not a diagnosis engine; the model is not the source of truth`
- 技术栈：
  - `FastAPI`
  - `React + Vite`
  - `SQLite cache`
  - `OpenAI / vLLM configurable`

### 演讲稿

“I want to frame this as an implemented MVP, not just a whiteboard architecture exercise.  
The system takes a clinical question, retrieves live evidence from ClinicalTrials.gov and PubMed, normalizes and reranks that evidence, and then uses an LLM to produce a grounded answer with citations and a pipeline trace.  
So in this walkthrough, I’m going to focus on four things: how I would structure the backend, how I query these two sources differently, how I surface accurate cited answers, and what tradeoffs I made along the way.”

### 需要展示的东西

- 先展示首页 UI 即可：
  - [frontend/src/App.tsx](/home/kleist/Documents/Code/medical_QA_system/frontend/src/App.tsx#L293)
- 让面试官先建立产品感。

### 时间

`2-3 分钟`

---

## Slide 2

### PPT 内容

标题：`How I Would Architect the Backend`

图上只画一条主链路：

`Frontend -> POST /api/qa -> QAService -> cache -> intent -> retrieval -> rerank -> answer generation -> citation validation -> response`

旁边列模块：

- `main.py`: API entrypoints
- `qa.py`: orchestration
- `clinicaltrials.py`: trial retrieval
- `pubmed.py`: literature retrieval
- `rerank.py`: evidence selection
- `llm_service.py`: provider-neutral LLM layer
- `cache.py`: query/source/embedding cache

### 演讲稿

“If I were designing this backend from scratch, I would separate orchestration from source-specific retrieval logic.  
The HTTP layer should stay thin and mostly handle schemas, dependency wiring, and lifecycle concerns.  
Then I would have one orchestration service that owns the end-to-end QA flow, separate services for ClinicalTrials.gov and PubMed, a provider-neutral LLM layer, and a separate cache layer.  
The reason is that these are different responsibilities with different failure modes.  
And that is basically how this repo is structured today. It is not one giant function. Retrieval, reranking, generation, validation, and caching are split into separate modules.”

### 需要展示的东西

- API 入口：
  - [backend/app/main.py](/home/kleist/Documents/Code/medical_QA_system/backend/app/main.py#L40)
- 主 orchestrator：
  - [backend/app/services/qa.py](/home/kleist/Documents/Code/medical_QA_system/backend/app/services/qa.py#L199)

### 时间

`3 分钟`

---

## Slide 3

### PPT 内容

标题：`API Design and Request Lifecycle`

左边列 API：

- `POST /api/qa`
- `GET /api/sources/{source_type}/{source_id}`
- `GET /api/health`

右边列 request stages：

- cache lookup
- intent extraction
- ClinicalTrials retrieval
- PubMed retrieval
- rerank
- answer generation
- citation validation
- final response

### 演讲稿

“On the API side, I would keep the main question-answering endpoint very simple.  
It should take the question, a small set of filters, and an evidence budget like max sources.  
Then I would separate source detail into a dedicated endpoint, because citation drill-down is important, but I do not want to overload the main response.  
I also like having a real health endpoint, not just a ping endpoint, so I can expose provider readiness and cache state.  
The other important design choice here is observability. In clinical QA, it is not enough to return an answer. You also need to understand why the system answered that way.”

### 需要展示的东西

- `POST /api/qa` / `GET /api/sources` / `GET /api/health`：
  - [backend/app/main.py](/home/kleist/Documents/Code/medical_QA_system/backend/app/main.py#L55)
- 真正的 pipeline stages：
  - [backend/app/services/qa.py](/home/kleist/Documents/Code/medical_QA_system/backend/app/services/qa.py#L212)
  - [backend/app/services/qa.py](/home/kleist/Documents/Code/medical_QA_system/backend/app/services/qa.py#L268)
  - [backend/app/services/qa.py](/home/kleist/Documents/Code/medical_QA_system/backend/app/services/qa.py#L302)

### 时间

`3 分钟`

---

## Slide 4

### PPT 内容

标题：`How I Structure Queries Against ClinicalTrials.gov`

列三点：

- structured fields, not raw sentence search
  - `query.cond`
  - `query.intr`
  - `query.term` fallback
- status-aware planning
  - recruiting
  - ongoing
- normalize into reusable snippet types
  - status
  - summary
  - eligibility
  - outcomes

### 演讲稿

“For ClinicalTrials.gov, I would not treat it like a generic search engine.  
I would translate the question into trial-registry semantics, especially condition, intervention, and status intent.  
So instead of sending the raw sentence, I try to populate fields like query.cond and query.intr, and I only fall back to a looser query.term when needed.  
Status-aware planning is especially important. A recruiting-trials question is really a structured filtering problem, not just a keyword problem.  
In fact, one real bug I fixed in this repo was exactly in this area. If you retrieve too few trials first and filter for recruiting afterward, you can miss the true recruiting matches.”

### 需要展示的东西

- Query planning：
  - [backend/app/services/clinicaltrials.py](/home/kleist/Documents/Code/medical_QA_system/backend/app/services/clinicaltrials.py#L71)
  - [backend/app/services/clinicaltrials.py](/home/kleist/Documents/Code/medical_QA_system/backend/app/services/clinicaltrials.py#L120)
- Recruiting / ongoing status inference：
  - [backend/app/services/clinicaltrials.py](/home/kleist/Documents/Code/medical_QA_system/backend/app/services/clinicaltrials.py#L111)
- Trial normalization into snippets：
  - [backend/app/services/clinicaltrials.py](/home/kleist/Documents/Code/medical_QA_system/backend/app/services/clinicaltrials.py#L169)

### 时间

`4 分钟`

---

## Slide 5

### PPT 内容

标题：`How I Structure Queries Against PubMed`

列三点：

- PubMed path is different:
  - `esearch -> esummary -> efetch`
- Query is built from:
  - condition
  - intervention
  - population
  - outcome intent
- Current grounding level:
  - `abstract-grounded`

### 演讲稿

“PubMed is a very different retrieval problem, so I would not force it into the same abstraction as trial registry search.  
Here I build a PubMed-style query from condition, intervention, population, and outcome intent, and I express that mostly as Title and Abstract clauses.  
Then I use a three-step path: esearch to get candidate PMIDs, esummary for metadata, and efetch for abstract text.  
That gives me a lightweight but reliable literature pipeline.  
The limitation I would state very clearly is that this MVP is mostly abstract-grounded, not full-text-grounded. I think being explicit about that is better than overstating the depth of evidence.”

### 需要展示的东西

- Query building：
  - [backend/app/services/pubmed.py](/home/kleist/Documents/Code/medical_QA_system/backend/app/services/pubmed.py#L60)
  - [backend/app/services/pubmed.py](/home/kleist/Documents/Code/medical_QA_system/backend/app/services/pubmed.py#L90)
- Metadata / abstract normalization：
  - [backend/app/services/pubmed.py](/home/kleist/Documents/Code/medical_QA_system/backend/app/services/pubmed.py#L145)

### 时间

`3-4 分钟`

---

## Slide 6

### PPT 内容

标题：`How I Surface Accurate, Cited Answers`

分四层：

- bounded evidence first
- hybrid reranking
- structured answer generation
- citation validation and fallback

右侧放一句核心原则：

`The model only synthesizes retrieved evidence; it never invents the evidence base.`

### 演讲稿

“My approach is not to trust the model first and ask for citations later.  
I do the opposite. I first build a bounded evidence window, and then I ask the model to synthesize only from that evidence.  
In this repo, the evidence is normalized into snippets, reranked, and then passed into a structured answer step rather than a free-form generation step.  
The model has to return citation IDs, and those citation IDs are validated against the retrieved snippets.  
If the citations do not validate, the system retries, and if support is still weak, it falls back to a conservative extractive answer.  
That fallback matters, because in a clinical setting, a conservative supported answer is usually better than a polished but unsupported one.”

### 需要展示的东西

- Reranker：
  - [backend/app/services/rerank.py](/home/kleist/Documents/Code/medical_QA_system/backend/app/services/rerank.py#L24)
- LLM structured outputs：
  - [backend/app/services/llm_service.py](/home/kleist/Documents/Code/medical_QA_system/backend/app/services/llm_service.py#L115)
  - [backend/app/services/llm_service.py](/home/kleist/Documents/Code/medical_QA_system/backend/app/services/llm_service.py#L152)
- Citation validation / normalization / fallback：
  - [backend/app/services/qa.py](/home/kleist/Documents/Code/medical_QA_system/backend/app/services/qa.py#L47)
  - [backend/app/services/qa.py](/home/kleist/Documents/Code/medical_QA_system/backend/app/services/qa.py#L54)
  - [backend/app/services/qa.py](/home/kleist/Documents/Code/medical_QA_system/backend/app/services/qa.py#L111)

### 时间

`4 分钟`

---

## Slide 7

### PPT 内容

标题：`Why the UI Matters for Trust`

列 UI blocks：

- direct answer
- why this answer
- limitations
- grouped citations
- source drawer
- pipeline trace drawer

### 演讲稿

“For me, trust is not only a backend problem. It is also a presentation problem.  
I want the user to see the direct answer, the supporting evidence, the limitations, and the citations as separate things.  
That is why the UI has a dedicated limitations section instead of hiding uncertainty inside one answer paragraph.  
I also do not treat citations as simple links. The source drawer lets the user inspect cached metadata and the available snippets behind each citation.  
And the pipeline trace makes the system less of a black box, which I think is especially important for medical or clinical use cases.”

### 需要展示的东西

- 前端结果页和三个 example questions：
  - [frontend/src/App.tsx](/home/kleist/Documents/Code/medical_QA_system/frontend/src/App.tsx#L298)
- Source drawer：
  - [frontend/src/App.tsx](/home/kleist/Documents/Code/medical_QA_system/frontend/src/App.tsx#L137)
- Trace drawer：
  - [frontend/src/App.tsx](/home/kleist/Documents/Code/medical_QA_system/frontend/src/App.tsx#L21)
- 主回答区域：
  - [frontend/src/App.tsx](/home/kleist/Documents/Code/medical_QA_system/frontend/src/App.tsx#L380)

### 时间

`3 分钟`

---

## Slide 8

### PPT 内容

标题：`Tradeoffs and Design Decisions`

做成两列：

左边：`What I chose`

- live retrieval + SQLite cache
- bounded reranking instead of vector DB
- provider-neutral OpenAI/vLLM layer
- abstract-grounded PubMed baseline
- single-turn UX

右边：`Why`

- faster to build, easier to debug
- main early risk is wrong routing / grounding, not scale
- easier to demo locally
- honest evidence depth
- keep trust and inspectability high

### 演讲稿

“If this were just an interview question, I would not give the easy answer of saying I would immediately add offline ingestion, a vector database, full-text pipelines, and an agent framework.  
I think the stronger answer is knowing what to add later and what not to add too early.  
For this MVP, I deliberately prioritized source-aware retrieval, grounded synthesis, citation validity, and debuggability over infrastructure complexity.  
So the main tradeoff is simplicity versus scale.  
I chose the simpler design because the early risk in clinical QA is usually not lack of infrastructure. It is wrong routing, weak grounding, and poor transparency.”

### 需要展示的东西

- Query cache key 里带 runtime context：
  - [backend/app/services/cache.py](/home/kleist/Documents/Code/medical_QA_system/backend/app/services/cache.py#L20)
- Provider-neutral runtime：
  - [backend/app/services/llm_service.py](/home/kleist/Documents/Code/medical_QA_system/backend/app/services/llm_service.py#L22)
  - [backend/app/services/llm_service.py](/home/kleist/Documents/Code/medical_QA_system/backend/app/services/llm_service.py#L241)

### 时间

`3-4 分钟`

---

## Slide 9

### PPT 内容

标题：`If I Had Another Week`

只列三个 next steps：

- stronger offline indexing
- evaluation by layer
- better blended-answer planning

### 演讲稿

“If I had another week, I would not spend it polishing the UI first.  
I would focus on three things.  
First, stronger offline indexing to improve latency, recall, and observability.  
Second, layered evaluation, so I am not only judging the final answer, but also route quality, retrieval quality, snippet relevance, and citation validity.  
Third, better planning for blended questions, because the hardest case right now is not a single-source question. It is synthesizing trial evidence and published literature together in a balanced way.”

### 需要展示的东西

- 不一定需要切代码。
- 这一页更适合纯讲。

### 时间

`2 分钟`

---

## 现场 Demo 建议

### 最适合现场跑的 3 个问题

1. `Are there any recruiting clinical trials for pembrolizumab in metastatic triple-negative breast cancer?`
   - 目的：展示 `trials` route
2. `What does the published literature say about the safety of semaglutide in adults with obesity?`
   - 目的：展示 `pubmed` route
3. `What trials are ongoing for CAR-T therapy in multiple myeloma and what published evidence already exists?`
   - 目的：展示 `blended` route

对应代码位置：

- [frontend/src/App.tsx](/home/kleist/Documents/Code/medical_QA_system/frontend/src/App.tsx#L6)

### Demo 时最值得点开的地方

- 先跑一个问题，看 answer blocks
- 点击一条 citation，打开 source drawer
- 再点 trace drawer，看 route / query params / top snippets

这三个动作已经足够，不要在现场来回切太多文件。

---

## 哪些代码最值得你亲自讲

优先级从高到低：

1. [backend/app/services/qa.py](/home/kleist/Documents/Code/medical_QA_system/backend/app/services/qa.py#L212)
   - 这是主 orchestrator，最能体现你的 backend instincts
2. [backend/app/services/clinicaltrials.py](/home/kleist/Documents/Code/medical_QA_system/backend/app/services/clinicaltrials.py#L120)
   - 最能体现你不是把 source 当全文检索在用
3. [backend/app/services/pubmed.py](/home/kleist/Documents/Code/medical_QA_system/backend/app/services/pubmed.py#L90)
   - 能体现 source-specific query design
4. [backend/app/services/qa.py](/home/kleist/Documents/Code/medical_QA_system/backend/app/services/qa.py#L47)
   - 能体现 citation validity 不是 prompt-only
5. [frontend/src/App.tsx](/home/kleist/Documents/Code/medical_QA_system/frontend/src/App.tsx#L21)
   - 能体现你考虑了 inspectability，而不是只做 answer box

---

## 不建议讲太多的东西

- 不要长时间讲 React 样式或视觉细节
- 不要过度展开 SQLite schema
- 不要花太久解释模型 prompt wording
- 不要把重点放在“这个系统已经 fully production-ready”

更好的姿势是：

`我知道哪里已经够说明我的架构判断，哪里还是 MVP tradeoff。`

---

## 最后 30 秒总结模板

你可以这样收尾：

“If I had to summarize the design in one sentence, it would be this: the model is not the source of truth, the retrieved evidence is.  
So most of my design decisions are really about making retrieval more source-aware, keeping the evidence window bounded, validating citations, and making the whole system inspectable.  
That is the bar I would want for any clinical QA product, even at the MVP stage.”
