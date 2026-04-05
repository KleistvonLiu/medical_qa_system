export type SourceType = "clinical_trials" | "pubmed";
export type RetrievalRoute = "trials" | "pubmed" | "blended";

export type QAFilters = {
  recruiting_only: boolean;
  recent_literature_only: boolean;
};

export type QARequest = {
  question: string;
  filters: QAFilters;
  max_sources: number;
};

export type Citation = {
  snippet_id: string;
  source_type: SourceType;
  source_id: string;
  identifier: string;
  title: string;
  section: string;
  text: string;
  url: string;
  published_at?: string | null;
  score: number;
};

export type TraceCard = {
  title: string;
  body: string;
};

export type TraceStage = {
  stage_id: string;
  title: string;
  status: "success" | "warning" | "error" | "skipped";
  summary: string;
  metrics: Record<string, string | number | boolean | null | undefined>;
  cards: TraceCard[];
  raw_json: Record<string, unknown>;
};

export type TraceSummary = {
  degraded: boolean;
  degraded_reason?: string | null;
  cache_hit: boolean;
  route: RetrievalRoute;
  total_ms: number;
};

export type PipelineTrace = {
  enabled: boolean;
  language: string;
  summary: TraceSummary;
  stages: TraceStage[];
};

export type QAResponse = {
  request_id: string;
  direct_answer: string;
  why_this_answer: string[];
  limitations: string[];
  citations: Citation[];
  source_groups: Record<string, Citation[]>;
  route: RetrievalRoute;
  cached: boolean;
  degraded: boolean;
  trace: PipelineTrace;
  debug: {
    request_id: string;
    cache_hit: boolean;
    cache_cleanup_at?: string;
    chat_provider: string;
    embedding_provider: string;
    chat_configured: boolean;
    embedding_configured: boolean;
    embeddings_enabled: boolean;
    source_counts: {
      clinical_trials: number;
      pubmed: number;
    };
    snippet_count: number;
    timings_ms: Record<string, number>;
  };
};

export type EvidenceSnippet = {
  snippet_id: string;
  source_type: SourceType;
  source_id: string;
  identifier: string;
  title: string;
  section: string;
  text: string;
  score: number;
  url: string;
  published_at?: string | null;
};

export type SourceDetail = {
  source_type: SourceType;
  source_id: string;
  identifier: string;
  title: string;
  url: string;
  published_at?: string | null;
  metadata: Record<string, unknown>;
  snippets: EvidenceSnippet[];
  cached_at: string;
};

export type HealthResponse = {
  status: string;
  sqlite_ok: boolean;
  chat_provider: string;
  embedding_provider: string;
  chat_configured: boolean;
  embedding_configured: boolean;
  last_cache_cleanup_at?: string | null;
};
