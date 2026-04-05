# Clinical QA MVP Interviewer Q&A

These answers are updated to match the code that exists in this repo today, not a purely hypothetical future architecture.

## 1. Is this a live retrieval system or an offline-ingested system?

### Answer

The current MVP uses live retrieval plus TTL-based local caching in SQLite. I chose that because it let me get an end-to-end product working quickly while keeping the retrieval path very transparent. If I were productionizing it, I would add a stronger offline indexing layer for better latency, recall, and observability.

### 中文提示

现在是 live retrieval + cache，不是假装已经有完整 offline ingestion。生产化时再补强 index。

## 2. Why support both OpenAI and vLLM?

### Answer

I wanted the backend to be provider-neutral. The same pipeline can run against OpenAI or a local vLLM server through config. That makes the architecture easier to test, cheaper to demo locally, and less coupled to one model vendor.

### 中文提示

provider-neutral 是工程价值，不是功能噱头。

## 3. How do you prevent hallucinations?

### Answer

I use layered controls. The system first retrieves bounded evidence, then the model only sees that evidence, then the backend validates citation IDs against the retrieved snippets, and if that fails the system falls back to a conservative extractive answer. So the model is constrained before generation and checked again after generation.

### 中文提示

bounded evidence, post-validation, fallback。不是只靠 prompt。

## 4. Why not use a vector database in the MVP?

### Answer

Because for this MVP, the bigger risks were wrong query translation and weak grounding, not large-scale vector search. A bounded hybrid reranker over live-retrieved candidates was enough to make the pipeline work and easier to debug. I would only add a vector index once I had clear evidence that recall was limited by candidate generation rather than by routing or source-aware retrieval.

### 中文提示

先解决 routing 和 grounding，再考虑大规模向量检索。

## 5. What happens if vLLM returns malformed structured output?

### Answer

The backend strips residual reasoning text, tries structured parsing, retries generation when needed, normalizes citations if the model returns a source identifier instead of a snippet identifier, and finally falls back to extractive mode if the answer is still unsupported. That makes local vLLM usage much more robust.

### 中文提示

thinking strip、retry、citation normalize、最后 fallback。

## 6. Why do you split trials and papers into different snippet types?

### Answer

Because the evidence lives in different places. For trials, the useful evidence is often status, eligibility, outcomes, or summary text. For PubMed, it is title, metadata, and abstract chunks. Keeping those source semantics separate improves both ranking and explanation quality.

### 中文提示

trial 和 paper 的 evidence shape 不一样，不能硬压成一样。

## 7. How do you debug bad answers?

### Answer

The product exposes a pipeline trace with eight stages: cache, intent, both retrieval branches, rerank, answer generation, citation validation, and final response. That means I can debug whether a bad answer came from routing, retrieval, ranking, or synthesis rather than treating the whole system as a black box.

### 中文提示

trace 是工程能力，不只是 demo feature。

## 8. What was one real bug you had to fix?

### Answer

A concrete example was recruiting trial search. Originally the system could miss recruiting trials because it retrieved a small number of trial records first and only filtered statuses afterward. I changed the ClinicalTrials search planning so recruiting-style questions use status-aware retrieval instead of truncating too early.

### 中文提示

给一个真实 bug，会显得你真的做过系统。

## 9. What was another real issue you saw with local models?

### Answer

One issue was citation formatting. The model would sometimes cite a `PMID` or `NCT` instead of the internal snippet ID that the backend expected. I added a normalization layer so the backend can map source identifiers back to retrieved snippets before validation. That reduced unnecessary fallback behavior.

### 中文提示

模型不是只会 hallucinate，也会“格式对不上”，这也是 production issue。

## 10. What is the weakest part of the current MVP?

### Answer

Blended summarization is still the hardest case. The retrieval layer now finds relevant trial and literature evidence, but the final answer can still under-summarize the full multi-source landscape. So the next improvement would be better answer planning and evidence budgeting for questions that ask for both ongoing trials and published evidence.

### 中文提示

真实弱点是 blended synthesis，不是 retrieval 已经完全没问题。

## 11. Why is PubMed only abstract-grounded?

### Answer

Because that is the most reliable public baseline for a lightweight MVP. PubMed metadata and abstracts are available through standard APIs, while full-text coverage depends on other pipelines, licensing, or open-access availability. I would rather be explicit about abstract-level grounding than imply a depth of evidence the system does not actually have.

### 中文提示

coverage 要诚实，不要夸系统。

## 12. How would you evaluate this system?

### Answer

I would evaluate it in layers: route correctness, source retrieval quality, snippet relevance, citation validity, and final answer usefulness. I would especially benchmark the three route families that the product already supports well: trials, PubMed, and blended.

### 中文提示

评测要分层，不要只看最后一句答得像不像。

## 13. If you had another week, what would you build next?

### Answer

I would build three things next: stronger offline indexing, a benchmark suite for representative clinical questions, and better answer planning for blended questions. I would prioritize those ahead of UI polish because the system's real value comes from evidence quality and synthesis reliability.

### 中文提示

下一周优先级：index、eval、blended planning。

## 14. Why is the frontend intentionally simple?

### Answer

Because in this product trust matters more than visual complexity. The frontend's main job is to expose the answer, the supporting evidence, the limitations, and the trace. A simpler UI made it easier to focus on inspectability.

### 中文提示

前端简洁是有意取舍，不是没做完。

## 15. What sentence would you use to summarize your design philosophy?

### Answer

`The model is not the source of truth. The retrieved evidence is the source of truth, and the system should make that visible.`

### 中文提示

收尾金句直接背。
