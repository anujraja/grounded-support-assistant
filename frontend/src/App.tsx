import { useEffect, useRef, useState } from "react";
import {
  decideTool,
  getAuditLog,
  getDocuments,
  getHealth,
  ingestSamples,
  streamChat,
  uploadDocument,
  type AuditEvent,
  type ChatMeta,
  type Citation,
  type DocumentRecord,
  type HealthResponse,
  type ToolDecisionResponse,
} from "./lib/api";

type TurnStatus = "streaming" | "done" | "error";
type RightTab = "sources" | "retrieval" | "approval" | "audit";

type ChatTurn = {
  id: string;
  question: string;
  answer: string;
  status: TurnStatus;
  error: string | null;
  meta: ChatMeta | null;
  toolDecision: ToolDecisionResponse | null;
};

const sampleQuestions = [
  "Why is my frontend trace not connecting to my backend service?",
  "What does the `sentry-trace` header do?",
  "Is JavaScript SDK version 99.0 supported?",
  "Delete the customer’s production project.",
  "Diagnose a problem that is not covered by the provided documents.",
];

const tabOrder: RightTab[] = ["sources", "retrieval", "approval", "audit"];

function createTurn(question: string): ChatTurn {
  return {
    id: crypto.randomUUID(),
    question,
    answer: "",
    status: "streaming",
    error: null,
    meta: null,
    toolDecision: null,
  };
}

function formatTime(value: string) {
  return new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  }).format(new Date(value));
}

function formatScore(value: number) {
  return value.toFixed(2);
}

function prettyToolName(name: string) {
  return name.replace(/_/g, " ");
}

function HealthPill({ health }: { health: HealthResponse | null }) {
  if (!health) {
    return (
      <div className="status-pill status-pill--loading">
        <span className="status-pill__dot status-pill__dot--pulse" />
        <span>Checking runtime</span>
      </div>
    );
  }

  return (
    <div
      className={`status-pill ${
        health.status === "ok" ? "status-pill--success" : "status-pill--warning"
      }`}
    >
      <span className="status-pill__dot" />
      <span>{health.status === "ok" ? "System ready" : "Degraded dependency"}</span>
    </div>
  );
}

function ConfidenceBadge({ label }: { label: ChatMeta["confidence"]["label"] }) {
  const tone =
    label === "High confidence"
      ? "badge--success"
      : label === "Medium confidence"
        ? "badge--warning"
        : "badge--danger";

  return <span className={`badge ${tone}`}>{label}</span>;
}

function EmptyState({
  title,
  detail,
  actionLabel,
  onAction,
}: {
  title: string;
  detail: string;
  actionLabel?: string;
  onAction?: () => void;
}) {
  return (
    <div className="empty-state">
      <div className="empty-state__icon" aria-hidden="true">
        <span className="empty-state__icon-ring" />
        <span className="empty-state__icon-bar empty-state__icon-bar--horizontal" />
        <span className="empty-state__icon-bar empty-state__icon-bar--vertical" />
      </div>
      <h3 className="empty-state__title">{title}</h3>
      <p className="empty-state__detail">{detail}</p>
      {actionLabel && onAction ? (
        <button className="button button--primary empty-state__action" onClick={onAction} type="button">
          {actionLabel}
        </button>
      ) : null}
    </div>
  );
}

function App() {
  const [question, setQuestion] = useState("");
  const [documents, setDocuments] = useState<DocumentRecord[]>([]);
  const [documentsLoading, setDocumentsLoading] = useState(true);
  const [documentsError, setDocumentsError] = useState<string | null>(null);
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [healthError, setHealthError] = useState<string | null>(null);
  const [audit, setAudit] = useState<AuditEvent[]>([]);
  const [auditLoading, setAuditLoading] = useState(true);
  const [auditError, setAuditError] = useState<string | null>(null);
  const [turns, setTurns] = useState<ChatTurn[]>([]);
  const [selectedTurnId, setSelectedTurnId] = useState<string | null>(null);
  const [selectedCitation, setSelectedCitation] = useState<number | null>(null);
  const [activeTab, setActiveTab] = useState<RightTab>("sources");
  const [pendingAction, setPendingAction] = useState<string | null>(null);
  const streamController = useRef<AbortController | null>(null);

  const selectedTurn =
    turns.find((turn) => turn.id === selectedTurnId) ?? turns[turns.length - 1] ?? null;
  const isStreaming = turns.some((turn) => turn.status === "streaming");

  async function refreshHealth() {
    setHealthError(null);
    try {
      setHealth(await getHealth());
    } catch (error) {
      setHealthError(error instanceof Error ? error.message : "Health check failed.");
    }
  }

  async function refreshDocuments() {
    setDocumentsLoading(true);
    setDocumentsError(null);
    try {
      setDocuments(await getDocuments());
    } catch (error) {
      setDocumentsError(error instanceof Error ? error.message : "Document list failed.");
    } finally {
      setDocumentsLoading(false);
    }
  }

  async function refreshAudit() {
    setAuditLoading(true);
    setAuditError(null);
    try {
      setAudit(await getAuditLog());
    } catch (error) {
      setAuditError(error instanceof Error ? error.message : "Audit feed failed.");
    } finally {
      setAuditLoading(false);
    }
  }

  useEffect(() => {
    void refreshHealth();
    void refreshDocuments();
    void refreshAudit();

    return () => {
      streamController.current?.abort();
    };
  }, []);

  function patchTurn(turnId: string, recipe: (turn: ChatTurn) => ChatTurn) {
    setTurns((current) =>
      current.map((turn) => (turn.id === turnId ? recipe(turn) : turn)),
    );
  }

  async function handleSendQuestion(customQuestion?: string) {
    const trimmed = (customQuestion ?? question).trim();
    if (!trimmed || isStreaming) {
      return;
    }

    const turn = createTurn(trimmed);
    streamController.current?.abort();
    streamController.current = new AbortController();
    setTurns((current) => [...current, turn]);
    setSelectedTurnId(turn.id);
    setSelectedCitation(null);
    setActiveTab("sources");
    setQuestion("");

    try {
      await streamChat(
        trimmed,
        {
          onMeta: (meta) => {
            patchTurn(turn.id, (item) => ({ ...item, meta }));
          },
          onToken: (token) => {
            patchTurn(turn.id, (item) => ({
              ...item,
              answer: `${item.answer}${token}`,
            }));
          },
          onError: (message) => {
            patchTurn(turn.id, (item) => ({
              ...item,
              status: "error",
              error: message,
            }));
          },
          onDone: async () => {
            patchTurn(turn.id, (item) => ({
              ...item,
              status: item.status === "error" ? "error" : "done",
            }));
            await refreshAudit();
          },
        },
        streamController.current.signal,
      );
    } catch (error) {
      const message =
        error instanceof Error ? error.message : "The question could not be completed.";
      patchTurn(turn.id, (item) => ({
        ...item,
        status: "error",
        error:
          message === "The user aborted a request."
            ? "Stream stopped by operator."
            : message,
      }));
    }
  }

  async function handleUpload(file: File | null) {
    if (!file) {
      return;
    }
    setPendingAction("upload");
    setDocumentsError(null);
    try {
      await uploadDocument(file);
      await Promise.all([refreshDocuments(), refreshHealth()]);
    } catch (error) {
      setDocumentsError(error instanceof Error ? error.message : "Upload failed.");
    } finally {
      setPendingAction(null);
    }
  }

  async function handleSampleIngest() {
    setPendingAction("ingest");
    setDocumentsError(null);
    try {
      await ingestSamples();
      await Promise.all([refreshDocuments(), refreshHealth()]);
    } catch (error) {
      setDocumentsError(error instanceof Error ? error.message : "Sample ingest failed.");
    } finally {
      setPendingAction(null);
    }
  }

  async function handleToolDecision(approved: boolean) {
    if (!selectedTurn?.meta?.tool_proposal) {
      return;
    }

    setPendingAction(approved ? "approve" : "reject");
    try {
      const decision = await decideTool(selectedTurn.meta.tool_proposal.id, approved);
      patchTurn(selectedTurn.id, (item) => ({ ...item, toolDecision: decision }));
      setActiveTab("audit");
      await refreshAudit();
    } catch (error) {
      patchTurn(selectedTurn.id, (item) => ({
        ...item,
        error:
          error instanceof Error ? error.message : "Tool decision failed to persist.",
        status: "error",
      }));
    } finally {
      setPendingAction(null);
    }
  }

  function openCitation(citationNumber: number) {
    setSelectedCitation(citationNumber);
    setActiveTab("sources");
  }

  function renderAnswer(answer: string, citations: Citation[]) {
    const parts = answer.split(/(\[\d+\])/g);
    return parts.map((part, index) => {
      const match = part.match(/^\[(\d+)\]$/);
      if (!match) {
        return (
          <span key={`${part}-${index}`} className="chat-answer__text">
            {part}
          </span>
        );
      }

      const citationNumber = Number(match[1]);
      const citationExists = citations.some((citation) => citation.number === citationNumber);
      if (!citationExists) {
        return <span key={`${part}-${index}`}>{part}</span>;
      }

      return (
        <button
          key={`${part}-${index}`}
          className="citation-inline"
          onClick={() => openCitation(citationNumber)}
          type="button"
        >
          {part}
        </button>
      );
    });
  }

  return (
    <div className="app-shell">
      <div className="app-shell__glow app-shell__glow--amber" />
      <div className="app-shell__glow app-shell__glow--blue" />
      <div className="app-shell__grid" />

      <div className="app-frame">
        <header className="panel topbar">
          <div className="topbar__copy">
            <div className="eyebrow">Local grounded runtime</div>
            <div className="topbar__headline">
              <h1 className="hero-title">Grounded Support Assistant</h1>
              <div className="topbar__meta-strip">
                <span className="topbar__meta-item">3-pane review console</span>
                <span className="topbar__meta-item">streamed evidence</span>
                <span className="topbar__meta-item">human tool gate</span>
              </div>
            </div>
            <p className="hero-copy">
              Inspect retrieved chunks, confidence, proposed tools, and audit history in one
              dense review surface.
            </p>
          </div>

          <div className="topbar__actions">
            <HealthPill health={health} />
            <button className="button button--secondary" onClick={() => void refreshHealth()} type="button">
              Refresh health
            </button>
          </div>
        </header>

        <div className="workspace">
          <aside className="workspace__left">
            <section className="panel section-card">
              <div className="section-card__header">
                <div>
                  <h2 className="section-title">Knowledge base</h2>
                  <p className="section-copy">Documents available to retrieval right now.</p>
                </div>
                <div className="meta-pill">{documents.length} docs</div>
              </div>

              {documentsLoading ? (
                <div className="stack">
                  {[0, 1, 2].map((item) => (
                    <div key={item} className="skeleton-card" />
                  ))}
                </div>
              ) : documentsError ? (
                <EmptyState
                  title="Document feed unavailable"
                  detail={documentsError}
                  actionLabel="Retry"
                  onAction={() => void refreshDocuments()}
                />
              ) : documents.length ? (
                <div className="stack">
                  {documents.map((document) => (
                    <article key={document.filename} className="info-card info-card--compact">
                      <div className="info-card__row">
                        <h3 className="info-card__title">{document.filename}</h3>
                        <span className="meta-pill meta-pill--small">{document.chunks} chunks</span>
                      </div>
                    </article>
                  ))}
                </div>
              ) : (
                <EmptyState
                  title="No documents ingested"
                  detail="Load the fictional sample corpus or upload a UTF-8 markdown/text file to make retrieval possible."
                  actionLabel="Load samples"
                  onAction={() => void handleSampleIngest()}
                />
              )}
            </section>

            <section className="panel section-card">
              <h2 className="section-title">Corpus actions</h2>
              <p className="section-copy">
                Every write path is explicit: upload one document, or re-run sample ingestion.
              </p>

              <div className="stack stack--spaced section-actions">
                <label className="button button--secondary button--block button--file">
                  <span>{pendingAction === "upload" ? "Uploading…" : "Upload .md or .txt"}</span>
                  <input
                    accept=".md,.txt,text/plain,text/markdown"
                    className="sr-only"
                    onChange={(event) => {
                      const file = event.target.files?.[0] ?? null;
                      void handleUpload(file);
                      event.target.value = "";
                    }}
                    type="file"
                  />
                </label>
                <button
                  className="button button--primary button--block"
                  disabled={pendingAction === "ingest"}
                  onClick={() => void handleSampleIngest()}
                  type="button"
                >
                  {pendingAction === "ingest" ? "Loading samples…" : "Ingest sample docs"}
                </button>
              </div>

              {healthError ? (
                <p className="notice notice--warning">Health check note: {healthError}</p>
              ) : null}
            </section>

            <section className="panel section-card">
              <h2 className="section-title">Prompt drills</h2>
              <p className="section-copy">
                Seed the demo with questions that exercise evidence, approval, and escalation.
              </p>
              <div className="stack stack--spaced section-actions">
                {sampleQuestions.map((prompt) => (
                  <button
                    key={prompt}
                    className="prompt-chip"
                    onClick={() => {
                      setQuestion(prompt);
                    }}
                    type="button"
                  >
                    <span className="prompt-chip__index" aria-hidden="true">
                      {String(sampleQuestions.indexOf(prompt) + 1).padStart(2, "0")}
                    </span>
                    <span className="prompt-chip__text">{prompt}</span>
                  </button>
                ))}
              </div>
            </section>

            <section className="panel section-card">
              <h2 className="section-title">Safety rails</h2>
              <div className="body-copy stack">
                <p>
                  Only stored proposals can execute. Destructive requests are refused before any
                  tool is suggested.
                </p>
                <p>
                  The right pane exposes raw retrieval scores, confidence heuristics, and the local
                  audit trail for each turn.
                </p>
              </div>
            </section>
          </aside>

          <main className="panel workspace__main chat-panel">
            <div className="chat-panel__header">
              <div>
                <h2 className="section-title">Operator chat</h2>
                <p className="section-copy">
                  Stream the answer, then inspect citations, retrieval debug, and approval state.
                </p>
              </div>
              {isStreaming ? (
                <button
                  className="button button--danger"
                  onClick={() => streamController.current?.abort()}
                  type="button"
                >
                  Stop stream
                </button>
              ) : null}
            </div>

            <div className="chat-thread">
              {turns.length === 0 ? (
                <EmptyState
                  title="No conversation yet"
                  detail="Ask a support question to start the streamed answer. When citations arrive, click them to inspect the retrieved chunks in the right pane."
                  actionLabel="Load starter question"
                  onAction={() => setQuestion(sampleQuestions[0])}
                />
              ) : (
                turns.map((turn) => {
                  const meta = turn.meta;
                  const isSelected = selectedTurn?.id === turn.id;
                  return (
                    <article
                      key={turn.id}
                      className={`chat-turn ${isSelected ? "chat-turn--selected" : ""}`}
                    >
                      <button
                        className="chat-turn__question"
                        onClick={() => setSelectedTurnId(turn.id)}
                        type="button"
                      >
                        <div className="chat-turn__question-row">
                          <span className="meta-pill meta-pill--small">Operator</span>
                          <span className="chat-turn__question-text">{turn.question}</span>
                        </div>
                      </button>

                      <div className="chat-turn__answer-shell">
                        <div className="chat-turn__answer-header">
                          <span className="meta-pill meta-pill--small">Assistant</span>
                          {meta ? <ConfidenceBadge label={meta.confidence.label} /> : null}
                          {turn.status === "streaming" ? (
                            <span className="badge badge--streaming">Streaming</span>
                          ) : null}
                        </div>

                        {meta?.confidence.escalation_recommended ? (
                          <div className="notice notice--warning">
                            Insufficient verified evidence. Escalation to a human support engineer is recommended.
                          </div>
                        ) : null}

                        {meta?.destructive_refusal ? (
                          <div className="notice notice--danger">
                            Destructive requests are blocked. No destructive tool is allowlisted in
                            this demo.
                          </div>
                        ) : null}

                        <div className="chat-answer">
                          {turn.answer ? renderAnswer(turn.answer, meta?.citations ?? []) : null}
                          {turn.status === "streaming" ? (
                            <span className="chat-answer__cursor" />
                          ) : null}
                        </div>

                        {turn.error ? (
                          <p className="notice notice--danger">{turn.error}</p>
                        ) : null}

                        {meta ? (
                          <div className="citation-row">
                            {meta.citations.map((citation) => (
                              <button
                                key={citation.chunk_id}
                                className={`citation-pill ${
                                  selectedCitation === citation.number
                                    ? "citation-pill--active"
                                    : ""
                                }`}
                                onClick={() => openCitation(citation.number)}
                                type="button"
                              >
                                [{citation.number}] {citation.filename}
                              </button>
                            ))}
                          </div>
                        ) : null}
                      </div>
                    </article>
                  );
                })
              )}
            </div>

            <form
              className="chat-form"
              onSubmit={(event) => {
                event.preventDefault();
                void handleSendQuestion();
              }}
            >
              <label className="form-label" htmlFor="question">
                Support question
              </label>
              <div className="chat-form__controls">
                <textarea
                  id="question"
                  className="chat-form__textarea"
                  onChange={(event) => setQuestion(event.target.value)}
                  placeholder="Ask a product support question that should stay grounded in the sample evidence."
                  value={question}
                />
                <div className="chat-form__actions">
                  <button
                    className="button button--primary button--tall"
                    disabled={!question.trim() || isStreaming}
                    type="submit"
                  >
                    {isStreaming ? "Streaming…" : "Send question"}
                  </button>
                  <button
                    className="button button--secondary button--tall"
                    onClick={() => setQuestion(sampleQuestions[1])}
                    type="button"
                  >
                    Use demo prompt
                  </button>
                </div>
              </div>
            </form>
          </main>

          <aside className="panel workspace__right inspector">
            <div className="inspector__header">
              <h2 className="section-title">Inspection pane</h2>
              <p className="section-copy">
                Choose a turn, then inspect sources, ranking signals, approval workflow, or audit.
              </p>
            </div>

            <div className="tabbar">
              {tabOrder.map((tab) => (
                <button
                  key={tab}
                  className={`tabbar__button ${activeTab === tab ? "tabbar__button--active" : ""}`}
                  onClick={() => setActiveTab(tab)}
                  type="button"
                >
                  {tab}
                </button>
              ))}
            </div>

            <div className="inspector__body">
              {activeTab === "sources" ? (
                selectedTurn?.meta ? (
                  <div className="stack stack--large">
                    <div className="info-card">
                      <p className="kicker">Confidence heuristic</p>
                      <p className="body-copy body-copy--paper">
                        {selectedTurn.meta.confidence.explanation}
                      </p>
                      <p className="micro-copy">{selectedTurn.meta.confidence.heuristic}</p>
                    </div>

                    {selectedTurn.meta.citations.map((citation) => (
                      <article
                        key={citation.chunk_id}
                        className={`info-card ${
                          selectedCitation === citation.number ? "info-card--active" : ""
                        }`}
                      >
                        <div className="info-card__row info-card__row--top">
                          <div>
                            <div className="kicker">Source [{citation.number}]</div>
                            <h3 className="info-card__title">{citation.filename}</h3>
                            <p className="info-card__subtitle">
                              {citation.heading || "Document body"}
                            </p>
                          </div>
                          <span className="meta-pill meta-pill--small">
                            Rank {citation.final_rank}
                          </span>
                        </div>
                        <p className="body-copy body-copy--paper">{citation.excerpt}</p>
                        <dl className="metric-grid">
                          <div className="metric-card">
                            <dt>Vector</dt>
                            <dd>{formatScore(citation.vector_score)}</dd>
                          </div>
                          <div className="metric-card">
                            <dt>BM25</dt>
                            <dd>{formatScore(citation.bm25_score)}</dd>
                          </div>
                          <div className="metric-card">
                            <dt>Fused</dt>
                            <dd>{formatScore(citation.combined_score)}</dd>
                          </div>
                        </dl>
                      </article>
                    ))}
                  </div>
                ) : (
                  <EmptyState
                    title="No sources yet"
                    detail="Sources appear after a streamed answer emits citation metadata."
                  />
                )
              ) : null}

              {activeTab === "retrieval" ? (
                selectedTurn?.meta ? (
                  <div className="stack stack--large">
                    <div className="metric-overview">
                      <div className="metric-overview__card">
                        <p className="kicker">Agreement</p>
                        <p className="metric-overview__value">
                          {formatScore(selectedTurn.meta.retrieval_debug.agreement)}
                        </p>
                      </div>
                      <div className="metric-overview__card">
                        <p className="kicker">Vector top</p>
                        <p className="metric-overview__value metric-overview__value--small">
                          {selectedTurn.meta.retrieval_debug.vector_top_ids.length}
                        </p>
                      </div>
                      <div className="metric-overview__card">
                        <p className="kicker">BM25 top</p>
                        <p className="metric-overview__value metric-overview__value--small">
                          {selectedTurn.meta.retrieval_debug.bm25_top_ids.length}
                        </p>
                      </div>
                    </div>

                    {selectedTurn.meta.reranker_error ? (
                      <div className="notice notice--warning">
                        Reranker note: {selectedTurn.meta.reranker_error}
                      </div>
                    ) : null}

                    {selectedTurn.meta.retrieval.map((chunk) => (
                      <article key={chunk.id} className="info-card">
                        <div className="info-card__row info-card__row--top">
                          <div>
                            <h3 className="info-card__title">{chunk.filename}</h3>
                            <p className="info-card__subtitle">
                              {chunk.heading || "Document body"}
                            </p>
                          </div>
                          <span className="meta-pill meta-pill--small">Rank {chunk.final_rank}</span>
                        </div>
                        <p className="body-copy body-copy--paper body-copy--clamp">{chunk.text}</p>
                        <dl className="metric-grid">
                          <div className="metric-card">
                            <dt>Vector</dt>
                            <dd>{formatScore(chunk.vector_score)}</dd>
                          </div>
                          <div className="metric-card">
                            <dt>BM25</dt>
                            <dd>{formatScore(chunk.bm25_score)}</dd>
                          </div>
                          <div className="metric-card">
                            <dt>Fused</dt>
                            <dd>{formatScore(chunk.combined_score)}</dd>
                          </div>
                        </dl>
                      </article>
                    ))}
                  </div>
                ) : (
                  <EmptyState
                    title="No retrieval trace yet"
                    detail="Hybrid retrieval details appear after the backend emits the first metadata event."
                  />
                )
              ) : null}

              {activeTab === "approval" ? (
                selectedTurn?.meta ? (
                  <div className="stack stack--large">
                    {selectedTurn.meta.tool_proposal ? (
                      <article className="info-card info-card--proposal">
                        <div className="info-card__row">
                          <div>
                            <p className="kicker">Proposed tool</p>
                            <h3 className="proposal-title">
                              {prettyToolName(selectedTurn.meta.tool_proposal.tool_name)}
                            </h3>
                          </div>
                          <span className="meta-pill meta-pill--small">
                            {formatTime(selectedTurn.meta.tool_proposal.created_at)}
                          </span>
                        </div>
                        <p className="body-copy body-copy--paper">
                          {selectedTurn.meta.tool_proposal.reason}
                        </p>
                        <pre className="code-block">
                          {JSON.stringify(selectedTurn.meta.tool_proposal.arguments, null, 2)}
                        </pre>

                        {selectedTurn.toolDecision ? (
                          <div className="stack stack--spaced">
                            <div
                              className={`notice ${
                                selectedTurn.toolDecision.approved
                                  ? "notice--success"
                                  : "notice--warning"
                              }`}
                            >
                              {selectedTurn.toolDecision.approved
                                ? "Proposal approved and executed."
                                : "Proposal rejected by operator."}
                            </div>
                            <pre className="code-block">
                              {JSON.stringify(selectedTurn.toolDecision.result, null, 2)}
                            </pre>
                          </div>
                        ) : (
                          <div className="decision-row">
                            <button
                              className="button button--primary button--grow"
                              disabled={pendingAction === "approve" || pendingAction === "reject"}
                              onClick={() => void handleToolDecision(true)}
                              type="button"
                            >
                              {pendingAction === "approve" ? "Approving…" : "Approve and execute"}
                            </button>
                            <button
                              className="button button--secondary button--grow"
                              disabled={pendingAction === "approve" || pendingAction === "reject"}
                              onClick={() => void handleToolDecision(false)}
                              type="button"
                            >
                              {pendingAction === "reject" ? "Rejecting…" : "Reject proposal"}
                            </button>
                          </div>
                        )}
                      </article>
                    ) : (
                      <EmptyState
                        title="No tool proposal"
                        detail={
                          selectedTurn.meta.destructive_refusal
                            ? "The backend refused the destructive request before any tool could be proposed."
                            : "This turn stayed within answer-only mode, so no tool approval was needed."
                        }
                      />
                    )}
                  </div>
                ) : (
                  <EmptyState
                    title="No approval context yet"
                    detail="Tool proposals are emitted in the same metadata event as citations and confidence."
                  />
                )
              ) : null}

              {activeTab === "audit" ? (
                auditLoading ? (
                  <div className="stack">
                    {[0, 1, 2].map((item) => (
                      <div key={item} className="skeleton-card skeleton-card--tall" />
                    ))}
                  </div>
                ) : auditError ? (
                  <EmptyState
                    title="Audit log unavailable"
                    detail={auditError}
                    actionLabel="Retry"
                    onAction={() => void refreshAudit()}
                  />
                ) : audit.length ? (
                  <div className="stack stack--large">
                    {audit.map((event) => (
                      <article key={event.id} className="info-card">
                        <div className="info-card__row">
                          <span className="meta-pill meta-pill--small">
                            {event.confidence ?? "Unknown confidence"}
                          </span>
                          <span className="micro-copy">{formatTime(event.timestamp)}</span>
                        </div>
                        <p className="body-copy body-copy--paper">{event.question}</p>
                        <div className="audit-tags">
                          <span className="meta-pill meta-pill--small">
                            {event.retrieved_chunk_ids.length} chunk ids
                          </span>
                          <span
                            className={`badge ${
                              event.tool_approved === true
                                ? "badge--success"
                                : event.tool_approved === false
                                  ? "badge--warning"
                                  : "badge--neutral"
                            }`}
                          >
                            {event.tool_approved === true
                              ? "Tool approved"
                              : event.tool_approved === false
                                ? "Tool rejected"
                                : "No tool decision"}
                          </span>
                          {event.escalation_recommended ? (
                            <span className="badge badge--danger">Escalation suggested</span>
                          ) : null}
                        </div>
                      </article>
                    ))}
                  </div>
                ) : (
                  <EmptyState
                    title="Audit trail is empty"
                    detail="Chat turns create audit entries after retrieval metadata is recorded."
                  />
                )
              ) : null}
            </div>
          </aside>
        </div>
      </div>
    </div>
  );
}

export default App;
