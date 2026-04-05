# Clinical QA 请求处理全流程

这份文档按当前代码实现，详细说明一个用户问题是如何一步一步变成最终答案的。它对应后端 `backend/app/services/qa.py` 的真实执行路径，也对应前端 `Pipeline Trace` 里看到的八个阶段。

## 1. 总览

当前系统的主链路是：

1. 前端收集问题和过滤条件
2. 调用 `POST /api/qa`
3. 后端做 cache lookup
4. 后端抽取 `QuestionIntent`
5. 后端按 route 分别调用 ClinicalTrials.gov / PubMed
6. 后端把原始 source 规范化成 `NormalizedSource`
7. 后端再把 source 切成 `EvidenceSnippet`
8. 后端对 snippets 做 hybrid rerank
9. 后端调用 LLM 生成结构化答案
10. 后端校验并归一化 citations
11. 后端拼装 `QAResponse`
12. 前端渲染 answer、limitations、citations、trace

## 2. 前端如何发起请求

前端入口在 `frontend/src/App.tsx`。

用户在页面里输入：

- `question`
- `recruiting_only`
- `recent_literature_only`
- `max_sources`

然后前端通过 `submitQuestion()` 调用后端：

```json
POST /api/qa
{
  "question": "...",
  "filters": {
    "recruiting_only": false,
    "recent_literature_only": false
  },
  "max_sources": 6
}
```

后端响应后，前端把结果渲染成：

- `direct_answer`
- `why_this_answer`
- `limitations`
- `source_groups`
- `trace`
- `debug`

## 3. 进入 FastAPI 路由

HTTP 入口在 `backend/app/main.py`。

核心路由是：

- `POST /api/qa`
- `GET /api/sources/{source_type}/{source_id}`
- `GET /api/health`

`POST /api/qa` 会创建 `QAService`，然后执行：

```python
response = await service.answer(session, payload)
```

真正的主编排逻辑都在 `backend/app/services/qa.py`。

## 4. Stage 1: Cache Lookup

trace 阶段名：`cache`

后端第一步会做三件事：

1. 生成 `request_id`
2. 清理过期缓存
3. 计算 `query_cache_key`

cache key 的组成在 `backend/app/services/cache.py`：

- 规范化后的 question
- filters
- `max_sources`
- runtime context

其中 runtime context 很重要，因为它会把当前 provider 信息也放进 key 里，例如：

- `chat_provider`
- `embedding_provider`
- `chat_configured`
- `embedding_configured`

这样可以避免“同一句问题在 OpenAI 模式和 vLLM 模式下共用同一份缓存”的问题。

如果 cache hit：

- 直接返回缓存的 `QAResponse`
- 但仍会更新 trace summary，让前端看到 `cache_hit = true`

如果 cache miss：

- 进入 live pipeline

## 5. Stage 2: Intent Analysis

trace 阶段名：`intent`

后端调用 `LLMService.extract_intent()` 生成一个 `QuestionIntent`。

结构是：

```json
{
  "route": "trials | pubmed | blended",
  "focus": "...",
  "condition_terms": [],
  "intervention_terms": [],
  "population_terms": [],
  "outcome_terms": [],
  "filters": {
    "recruiting_only": false,
    "recent_literature_only": false
  }
}
```

当前实现里，LLM 层在 `backend/app/services/llm_service.py`。它支持两种模式：

- `CHAT_PROVIDER=openai`
- `CHAT_PROVIDER=vllm`

intent 提取走的是结构化 JSON schema 输出。

如果 LLM 不可用或结构化解析失败：

- 会退回 `_heuristic_intent()`

### 三个问题在这一步怎么被分流

1. `Are there any recruiting clinical trials for pembrolizumab in metastatic triple-negative breast cancer?`
   - route: `trials`
2. `What does the published literature say about the safety of semaglutide in adults with obesity?`
   - route: `pubmed`
3. `What trials are ongoing for CAR-T therapy in multiple myeloma and what published evidence already exists?`
   - route: `blended`

## 6. Stage 3: ClinicalTrials.gov Retrieval

trace 阶段名：`clinical_trials_retrieval`

只有当 route 是 `trials` 或 `blended` 时才执行。

核心实现文件：

- `backend/app/services/clinicaltrials.py`

### 查询构造

后端不会直接把用户整句英文丢给 ClinicalTrials.gov。

它会先构造更结构化的查询参数，例如：

- `query.cond`
- `query.intr`
- `query.term`

当前还加了状态感知逻辑：

- 如果问题里明显是在问 `recruiting`
  - 会优先加 recruiting-oriented 过滤
- 如果问题里是在问 `ongoing`
  - 会扩搜索窗口，再保留 ongoing 相关状态

这一步是这次 debug 的一个重点，因为早期版本曾经犯过一个错误：

- 先只取前几条 trial
- 再本地过滤 recruiting status

这会导致真正 recruiting 的 trial 被截断掉，最终系统误答“没有 recruiting trial”。

现在修完之后，这个问题已经解决。

### 规范化

ClinicalTrials 返回后，后端会把 study 规范化成 `NormalizedSource`。

保留的信息包括：

- `source_id`
- `identifier`
- `title`
- `url`
- `published_at`
- `metadata`
- `snippets`

trial 侧的 snippet 通常来自：

- `status`
- `summary`
- `eligibility`
- `outcomes`

### 例子

对问题 1，实际 query 会接近：

```json
{
  "pageSize": 20,
  "query.cond": "metastatic triple-negative breast cancer",
  "query.intr": "pembrolizumab",
  "filter.overallStatus": "RECRUITING"
}
```

## 7. Stage 4: PubMed Retrieval

trace 阶段名：`pubmed_retrieval`

只有当 route 是 `pubmed` 或 `blended` 时才执行。

核心实现文件：

- `backend/app/services/pubmed.py`

### 调用链

PubMed 不是一次请求拿全。

当前实现是：

1. `esearch`
   - 找 PMID 列表
2. `esummary`
   - 拉 metadata
3. `efetch`
   - 拉 abstract XML

然后后端把 XML 里的 abstract 拆出来。

### 查询构造

PubMed query 会用 condition / intervention / outcome 拼成 `Title/Abstract` 风格的查询。

例如对问题 2，实际 search term 是：

```text
("adults with obesity"[Title/Abstract]) AND ("semaglutide"[Title/Abstract]) AND ("safety"[Title/Abstract])
```

这一步也是这次 debug 里修过的地方：

- 以前如果 LLM 没抽出 terms，就容易把整句问题直接塞进 PubMed
- 结果得到 `0` 条
- 现在会做更稳的 term inference

### 规范化

PubMed source 会被切成这些 snippet：

- `title`
- `metadata`
- `abstract_1`
- `abstract_2`
- ...

PubMed 侧当前是 `abstract-grounded`，这意味着：

- 如果没有额外 full-text pipeline
- 系统只能保证回答忠实于 title / metadata / abstract

## 8. Stage 5: Snippet Reranking

trace 阶段名：`rerank`

所有 source 的 snippets 会被 flatten 成一个列表，然后交给 `backend/app/services/rerank.py`。

当前打分是 hybrid 的：

- upstream `source_rank`
- `keyword_overlap`
- `embedding cosine`

但 embedding 是可选的。

当前本地推荐模式通常是：

```env
CHAT_PROVIDER=vllm
EMBED_PROVIDER=none
```

所以本地多数时候实际上是：

- `source_rank + keyword_overlap`

并且做了一个重要修复：

- 同一个 source 最多只占一部分 top-k
- 避免一个 paper 或一个 trial 把证据窗口挤满

这个 source diversity 对问题 2 和问题 3 都很重要。

## 9. Stage 6: Answer Generation

trace 阶段名：`answer_generation`

后端把 top snippets 打包成 evidence payload，然后调用 `LLMService.compose_answer()`。

输出 schema 是：

```json
{
  "direct_answer": "...",
  "why_this_answer": ["..."],
  "limitations": ["..."],
  "citation_ids": ["..."]
}
```

### 这里的几个关键工程细节

1. 同一套代码兼容 OpenAI 和 vLLM
   - 走的是 OpenAI-compatible chat completions + JSON schema

2. vLLM 可能会混入思维文本
   - 后端会 strip `thinking` 内容

3. 模型有时会返回错格式的 citation
   - 例如返回 `PMID:36216945`
   - 但后端真正需要的是 `snippet_id`

这次 debug 里我补了 citation normalization：

- 如果模型给的是 `PMID` 或 `source_id`
- 后端会尽量映射回检索到的 snippet

这解决了一个很真实的问题：

- 问题 2 明明答得出来
- 但因为 citation 格式不对，被系统自己降级成 extractive fallback

## 10. Stage 7: Citation Validation

trace 阶段名：`citation_validation`

当前系统不是“模型写了 citation 就信了”。

后端会检查：

- `citation_ids` 是否都存在于当前 reranked snippets 里

如果不通过：

- 会重试结构化生成
- 仍不通过就 fallback

这使得系统更保守，也更可信。

## 11. Stage 8: Final Response Assembly

trace 阶段名：`final_response`

通过 citation validation 后，后端会：

1. 把 `snippet_id` 变成真正的 `Citation`
2. 按 source type 分组，形成 `source_groups`
3. 组装 `QAResponse`
4. 记录 debug 信息
5. 构建完整的 `PipelineTrace`
6. 写入 query cache
7. 写入轻量级 `RequestTrace`

最终返回给前端的核心字段是：

- `direct_answer`
- `why_this_answer`
- `limitations`
- `citations`
- `source_groups`
- `route`
- `cached`
- `degraded`
- `trace`
- `debug`

## 12. 前端如何展示结果

前端拿到 `QAResponse` 后，会展示：

### 主结果区

- `Direct answer`
- `Why this answer`
- `Limitations`
- `Citations`

### Source drawer

点击 citation 之后，前端会请求：

```text
GET /api/sources/{source_type}/{source_id}
```

然后展示：

- source metadata
- source snippets
- 原始外链

### Pipeline trace drawer

如果点击 `View pipeline trace`，前端会展示每个阶段的：

- status
- summary
- metrics
- cards
- raw JSON

这也是为什么这个系统在 debug 时非常有用。

## 13. 用三个真实问题串起来看

### 问题 1

`Are there any recruiting clinical trials for pembrolizumab in metastatic triple-negative breast cancer?`

处理路径：

1. route -> `trials`
2. ClinicalTrials 构造 status-aware query
3. 命中多个 recruiting `NCT`
4. rerank 后保留 trial snippets
5. LLM 生成 answer
6. 返回 recruiting trial 结论和 `NCT` citations

### 问题 2

`What does the published literature say about the safety of semaglutide in adults with obesity?`

处理路径：

1. route -> `pubmed`
2. PubMed 构造 semaglutide + obesity + safety 查询
3. 命中 `PMID 36216945` 等文献
4. 切出 title / abstract snippets
5. LLM 生成结构化答案
6. citation normalization 把 `PMID` 映射回 snippet
7. 返回 grounded answer，不再错误 fallback

### 问题 3

`What trials are ongoing for CAR-T therapy in multiple myeloma and what published evidence already exists?`

处理路径：

1. route -> `blended`
2. ClinicalTrials 命中 ongoing CAR-T trial
3. PubMed 命中 CAR-T / multiple myeloma 相关文献
4. rerank 合并 trials + literature evidence
5. LLM 输出综合回答
6. 返回一个 blended answer，同时给出 `NCT` 和 `PMID`

当前剩余限制：

- retrieval 已经能找到多个相关 trial
- 但最终 answer 还可能不够完整地枚举整个 ongoing trial landscape

也就是说，现在的短板更偏向 answer planning，而不是 source retrieval。

## 14. 当前系统最重要的设计判断

如果把这个系统压缩成一句话，就是：

`先把问题拆开，按 source 正确检索，再把证据限制在一个可验证的窗口内，最后才允许模型写答案。`

这就是为什么它虽然是一个小 MVP，但已经具备比较好的可解释性和可调试性。
