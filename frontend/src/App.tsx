import { FormEvent, startTransition, useEffect, useMemo, useState } from "react";

import { fetchSourceDetail, submitQuestion } from "./api";
import type { Citation, PipelineTrace, QAResponse, SourceDetail, TraceStage } from "./types";

const EXAMPLE_QUESTIONS = [
  "Are there any recruiting clinical trials for pembrolizumab in metastatic triple-negative breast cancer?",
  "What does the published literature say about the safety of semaglutide in adults with obesity?",
  "What trials are ongoing for CAR-T therapy in multiple myeloma and what published evidence already exists?",
];

const DEFAULT_MAX_SOURCES = 6;

function statusLabel(status: TraceStage["status"]) {
  if (status === "success") return "Success";
  if (status === "warning") return "Warning";
  if (status === "error") return "Error";
  return "Skipped";
}

function TraceDrawer({
  trace,
  onClose,
}: {
  trace: PipelineTrace | null;
  onClose: () => void;
}) {
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});

  useEffect(() => {
    setExpanded({});
  }, [trace]);

  if (!trace) {
    return null;
  }

  return (
    <aside className="drawer drawer--trace">
      <div className="drawer__header">
        <div>
          <p className="eyebrow">Pipeline Trace</p>
          <h3>Step-by-step processing</h3>
        </div>
        <button className="ghost-button" onClick={onClose} type="button">
          Close
        </button>
      </div>
      <div className="drawer__content">
        <div className="meta-grid">
          <div>
            <span className="meta-label">Route</span>
            <p>{trace.summary.route}</p>
          </div>
          <div>
            <span className="meta-label">Cache</span>
            <p>{trace.summary.cache_hit ? "hit" : "miss"}</p>
          </div>
          <div>
            <span className="meta-label">Total ms</span>
            <p>{trace.summary.total_ms}</p>
          </div>
        </div>

        {trace.summary.degraded_reason ? (
          <div className="snippet-card">
            <span className="meta-label">Degraded reason</span>
            <p>{trace.summary.degraded_reason}</p>
          </div>
        ) : null}

        <div className="trace-timeline">
          {trace.stages.map((stage) => {
            const isExpanded = expanded[stage.stage_id] ?? false;
            return (
              <article key={stage.stage_id} className={`trace-stage trace-stage--${stage.status}`}>
                <div className="trace-stage__header">
                  <div>
                    <p className="eyebrow">{stage.stage_id}</p>
                    <h4>{stage.title}</h4>
                  </div>
                  <span className={`trace-badge trace-badge--${stage.status}`}>
                    {statusLabel(stage.status)}
                  </span>
                </div>
                <p className="trace-stage__summary">{stage.summary}</p>

                {Object.keys(stage.metrics).length ? (
                  <div className="trace-metrics">
                    {Object.entries(stage.metrics).map(([key, value]) => (
                      <div key={key} className="trace-metric">
                        <span className="meta-label">{key}</span>
                        <p>{String(value)}</p>
                      </div>
                    ))}
                  </div>
                ) : null}

                {stage.cards.length ? (
                  <div className="trace-cards">
                    {stage.cards.map((item, index) => (
                      <div key={`${stage.stage_id}-${index}`} className="snippet-card">
                        <span className="meta-label">{item.title}</span>
                        <p>{item.body}</p>
                      </div>
                    ))}
                  </div>
                ) : null}

                <button
                  className="ghost-button"
                  type="button"
                  onClick={() =>
                    setExpanded((current) => ({
                      ...current,
                      [stage.stage_id]: !isExpanded,
                    }))
                  }
                >
                  {isExpanded ? "Hide raw JSON" : "Show raw JSON"}
                </button>

                {isExpanded ? (
                  <div className="snippet-card">
                    <pre>{JSON.stringify(stage.raw_json, null, 2)}</pre>
                  </div>
                ) : null}
              </article>
            );
          })}
        </div>
      </div>
    </aside>
  );
}

function SourceDrawer({
  citation,
  detail,
  loading,
  onClose,
}: {
  citation: Citation | null;
  detail: SourceDetail | null;
  loading: boolean;
  onClose: () => void;
}) {
  if (!citation) {
    return null;
  }

  return (
    <aside className="drawer">
      <div className="drawer__header">
        <div>
          <p className="eyebrow">Source Detail</p>
          <h3>{citation.title}</h3>
        </div>
        <button className="ghost-button" onClick={onClose} type="button">
          Close
        </button>
      </div>
      <div className="drawer__content">
        <div className="meta-grid">
          <div>
            <span className="meta-label">Identifier</span>
            <p>{citation.identifier}</p>
          </div>
          <div>
            <span className="meta-label">Source</span>
            <p>{citation.source_type === "clinical_trials" ? "ClinicalTrials.gov" : "PubMed"}</p>
          </div>
          <div>
            <span className="meta-label">Published</span>
            <p>{citation.published_at ?? "Not provided"}</p>
          </div>
          <div>
            <span className="meta-label">Section</span>
            <p>{citation.section}</p>
          </div>
        </div>

        <div className="snippet-card">
          <span className="meta-label">Selected snippet</span>
          <p>{citation.text}</p>
        </div>

        {loading ? <p className="muted">Loading source metadata...</p> : null}

        {detail ? (
          <>
            <div className="snippet-card">
              <span className="meta-label">Cached at</span>
              <p>{detail.cached_at}</p>
            </div>
            <div className="snippet-card">
              <span className="meta-label">Metadata</span>
              <pre>{JSON.stringify(detail.metadata, null, 2)}</pre>
            </div>
            <div className="snippet-stack">
              <span className="meta-label">Available snippets</span>
              {detail.snippets.map((snippet) => (
                <article key={snippet.snippet_id} className="snippet-card">
                  <strong>{snippet.section}</strong>
                  <p>{snippet.text}</p>
                </article>
              ))}
            </div>
          </>
        ) : null}

        <a className="primary-button" href={citation.url} target="_blank" rel="noreferrer">
          Open original source
        </a>
      </div>
    </aside>
  );
}

export default function App() {
  const [question, setQuestion] = useState(EXAMPLE_QUESTIONS[0]);
  const [recruitingOnly, setRecruitingOnly] = useState(false);
  const [recentOnly, setRecentOnly] = useState(false);
  const [maxSources, setMaxSources] = useState(DEFAULT_MAX_SOURCES);
  const [result, setResult] = useState<QAResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [selectedCitation, setSelectedCitation] = useState<Citation | null>(null);
  const [selectedDetail, setSelectedDetail] = useState<SourceDetail | null>(null);
  const [drawerLoading, setDrawerLoading] = useState(false);
  const [traceOpen, setTraceOpen] = useState(false);

  const groupedCitations = useMemo(() => result?.source_groups ?? {}, [result]);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setLoading(true);
    setError(null);
    setSelectedCitation(null);
    setSelectedDetail(null);
    setTraceOpen(false);
    try {
      const response = await submitQuestion({
        question,
        filters: {
          recruiting_only: recruitingOnly,
          recent_literature_only: recentOnly,
        },
        max_sources: maxSources,
      });
      startTransition(() => setResult(response));
    } catch (submissionError) {
      setResult(null);
      setError(
        submissionError instanceof Error
          ? submissionError.message
          : "Request failed unexpectedly.",
      );
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    let cancelled = false;
    if (!selectedCitation) {
      return undefined;
    }
    setDrawerLoading(true);
    setSelectedDetail(null);
    fetchSourceDetail(selectedCitation.source_type, selectedCitation.source_id)
      .then((detail) => {
        if (!cancelled) {
          setSelectedDetail(detail);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setSelectedDetail(null);
        }
      })
      .finally(() => {
        if (!cancelled) {
          setDrawerLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [selectedCitation]);

  return (
    <div className="app-shell">
      <div className="hero-glow hero-glow--one" />
      <div className="hero-glow hero-glow--two" />
      <main className="layout">
        <section className="hero">
          <p className="eyebrow">Clinical QA MVP</p>
          <h1>Ask clinical questions, inspect evidence, and verify every citation.</h1>
          <p className="hero-copy">
            This demo retrieves live evidence from ClinicalTrials.gov and PubMed, then
            produces a grounded answer with explicit source snippets and conservative
            limitations.
          </p>

          <div className="example-strip">
            {EXAMPLE_QUESTIONS.map((example) => (
              <button
                key={example}
                className="example-chip"
                type="button"
                onClick={() => setQuestion(example)}
              >
                {example}
              </button>
            ))}
          </div>
        </section>

        <section className="panel panel--composer">
          <form onSubmit={handleSubmit}>
            <label className="field-label" htmlFor="question">
              Question
            </label>
            <textarea
              id="question"
              className="question-box"
              value={question}
              onChange={(event) => setQuestion(event.target.value)}
              placeholder="Ask a clinical question..."
            />

            <div className="controls-grid">
              <label className="toggle">
                <input
                  checked={recruitingOnly}
                  onChange={(event) => setRecruitingOnly(event.target.checked)}
                  type="checkbox"
                />
                <span>Recruiting trials only</span>
              </label>

              <label className="toggle">
                <input
                  checked={recentOnly}
                  onChange={(event) => setRecentOnly(event.target.checked)}
                  type="checkbox"
                />
                <span>Recent literature only</span>
              </label>

              <label className="range-control">
                <span>Max sources</span>
                <input
                  type="range"
                  min={3}
                  max={8}
                  value={maxSources}
                  onChange={(event) => setMaxSources(Number(event.target.value))}
                />
                <strong>{maxSources}</strong>
              </label>
            </div>

            <div className="action-row">
              <button className="primary-button" disabled={loading} type="submit">
                {loading ? "Searching sources..." : "Ask the system"}
              </button>
              {result ? (
                <span className="status-pill">
                  Route: {result.route} {result.cached ? "• cached" : "• live"}
                </span>
              ) : null}
            </div>
          </form>
          {error ? <p className="error-banner">{error}</p> : null}
        </section>

        <div className="results-grid">
          <section className="panel">
            <div className="section-header">
              <div>
                <p className="eyebrow">Answer</p>
                <h2>Direct answer</h2>
              </div>
              {result?.degraded ? <span className="warning-badge">Degraded mode</span> : null}
            </div>
            <p className="answer-copy">
              {result?.direct_answer ??
                "Submit a question to generate a source-grounded answer from ClinicalTrials.gov and PubMed."}
            </p>
          </section>

          <section className="panel">
            <div className="section-header">
              <div>
                <p className="eyebrow">Evidence</p>
                <h2>Why this answer</h2>
              </div>
            </div>
            {result?.why_this_answer.length ? (
              <ul className="list-block">
                {result.why_this_answer.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            ) : (
              <p className="muted">The evidence summary will appear here.</p>
            )}
          </section>

          <section className="panel">
            <div className="section-header">
              <div>
                <p className="eyebrow">Risk</p>
                <h2>Limitations and conflicts</h2>
              </div>
            </div>
            {result?.limitations.length ? (
              <ul className="list-block">
                {result.limitations.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            ) : (
              <p className="muted">
                Limitations and uncertainty handling will be shown separately from the main answer.
              </p>
            )}
          </section>

          <section className="panel panel--wide">
            <div className="section-header">
              <div>
                <p className="eyebrow">Sources</p>
                <h2>Citations</h2>
              </div>
            </div>

            {Object.keys(groupedCitations).length ? (
              <div className="citation-groups">
                {Object.entries(groupedCitations).map(([sourceType, citations]) => (
                  <section key={sourceType} className="citation-group">
                    <header>
                      <h3>
                        {sourceType === "clinical_trials" ? "ClinicalTrials.gov" : "PubMed"}
                      </h3>
                      <span>{citations.length} cited snippets</span>
                    </header>
                    <div className="citation-list">
                      {citations.map((citation) => (
                        <button
                          key={citation.snippet_id}
                          className="citation-card"
                          type="button"
                          onClick={() => setSelectedCitation(citation)}
                        >
                          <div className="citation-card__meta">
                            <span>{citation.identifier}</span>
                            <span>{citation.section}</span>
                          </div>
                          <strong>{citation.title}</strong>
                          <p>{citation.text}</p>
                        </button>
                      ))}
                    </div>
                  </section>
                ))}
              </div>
            ) : (
              <p className="muted">Citations will be grouped by source after a successful answer.</p>
            )}
          </section>
        </div>

        <section className="panel panel--debug">
          <div className="section-header">
            <div>
              <p className="eyebrow">Debug</p>
              <h2>Request trace</h2>
            </div>
          </div>
          {result ? (
            <div className="debug-grid">
              <div>
                <span className="meta-label">Route</span>
                <p>{result.route}</p>
              </div>
              <div>
                <span className="meta-label">Chat provider</span>
                <p>{result.debug.chat_provider}</p>
              </div>
              <div>
                <span className="meta-label">Embed provider</span>
                <p>{result.debug.embedding_provider}</p>
              </div>
              <div>
                <span className="meta-label">Cache</span>
                <p>{result.cached ? "hit" : "miss"}</p>
              </div>
              <div>
                <span className="meta-label">Embeddings</span>
                <p>{result.debug.embeddings_enabled ? "enabled" : "disabled"}</p>
              </div>
              <div>
                <span className="meta-label">ClinicalTrials count</span>
                <p>{result.debug.source_counts.clinical_trials}</p>
              </div>
              <div>
                <span className="meta-label">PubMed count</span>
                <p>{result.debug.source_counts.pubmed}</p>
              </div>
              <div>
                <span className="meta-label">Snippet count</span>
                <p>{result.debug.snippet_count}</p>
              </div>
              <div>
                <span className="meta-label">Request ID</span>
                <p>{result.request_id}</p>
              </div>
            </div>
          ) : (
            <p className="muted">Debug metadata will appear after the first query.</p>
          )}
          {result?.trace ? (
            <div className="action-row">
              <button className="ghost-button" type="button" onClick={() => setTraceOpen(true)}>
                View pipeline trace
              </button>
            </div>
          ) : (
            <p className="muted">Pipeline trace will appear after the first query.</p>
          )}
        </section>
      </main>

      <SourceDrawer
        citation={selectedCitation}
        detail={selectedDetail}
        loading={drawerLoading}
        onClose={() => {
          setSelectedCitation(null);
          setSelectedDetail(null);
        }}
      />
      <TraceDrawer trace={traceOpen ? result?.trace ?? null : null} onClose={() => setTraceOpen(false)} />
    </div>
  );
}
