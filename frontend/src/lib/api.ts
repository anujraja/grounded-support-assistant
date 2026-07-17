export type HealthResponse = {
  status: "ok" | "degraded";
  dependencies: {
    chroma: { status: string; chunks: number };
    ollama: {
      status: "ok" | "unavailable";
      model_configured?: string;
      model_available?: boolean;
      error?: string;
      help?: string;
    };
    reranker: { enabled: boolean; last_error: string | null };
  };
};

export type DocumentRecord = {
  filename: string;
  chunks: number;
};

export type IngestResponse = {
  ingested_chunks: number;
  skipped_duplicates: number;
  files: string[];
};

export type ConfidenceResult = {
  label: "High confidence" | "Medium confidence" | "Low confidence";
  score: number;
  explanation: string;
  escalation_recommended: boolean;
  heuristic: string;
};

export type Citation = {
  number: number;
  chunk_id: string;
  filename: string;
  heading: string;
  excerpt: string;
  vector_score: number;
  bm25_score: number;
  combined_score: number;
  final_rank: number;
};

export type RetrievalChunk = {
  id: string;
  text: string;
  filename: string;
  heading: string;
  created_at: string;
  doc_hash: string;
  vector_score: number;
  bm25_score: number;
  combined_score: number;
  final_rank: number;
  rerank_score?: number | null;
};

export type RetrievalDebug = {
  vector_top_ids: string[];
  bm25_top_ids: string[];
  agreement: number;
};

export type ToolProposal = {
  id: string;
  tool_name:
    | "check_supported_sdk_version"
    | "inspect_trace_headers"
    | "create_escalation_summary";
  arguments: Record<string, unknown>;
  reason: string;
  created_at: string;
};

export type ToolDecisionResponse = {
  proposal: ToolProposal;
  approved: boolean;
  result: Record<string, unknown> | null;
};

export type AuditEvent = {
  id: string;
  timestamp: string;
  question: string;
  retrieved_chunk_ids: string[];
  tool_proposal_id: string | null;
  tool_proposed: string | null;
  tool_approved: boolean | null;
  tool_result: Record<string, unknown> | null;
  confidence: string | null;
  escalation_recommended: boolean;
};

export type ChatMeta = {
  citations: Citation[];
  retrieval: RetrievalChunk[];
  retrieval_debug: RetrievalDebug;
  confidence: ConfidenceResult;
  tool_proposal: ToolProposal | null;
  audit_id: string;
  destructive_refusal: boolean;
  reranker_error: string | null;
};

type EventHandlers = {
  onMeta: (meta: ChatMeta) => void;
  onToken: (token: string) => void;
  onError: (message: string) => void;
  onDone: (payload: { audit_id?: string }) => void;
};

const apiBase = (import.meta.env.VITE_API_BASE_URL ?? "").replace(/\/$/, "");

function toUrl(path: string) {
  return `${apiBase}${path}`;
}

async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(toUrl(path), init);
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(detail || `Request failed with ${response.status}`);
  }
  return (await response.json()) as T;
}

function parseEventBlock(rawBlock: string) {
  const lines = rawBlock.split("\n");
  let eventName = "message";
  const payloadLines: string[] = [];
  for (const line of lines) {
    if (line.startsWith("event:")) {
      eventName = line.slice(6).trim();
    }
    if (line.startsWith("data:")) {
      payloadLines.push(line.slice(5).trim());
    }
  }
  if (!payloadLines.length) {
    return null;
  }
  return {
    eventName,
    payload: JSON.parse(payloadLines.join("\n")) as unknown,
  };
}

export async function getHealth() {
  return requestJson<HealthResponse>("/health");
}

export async function getDocuments() {
  return requestJson<DocumentRecord[]>("/api/documents");
}

export async function ingestSamples() {
  return requestJson<IngestResponse>("/api/ingest", { method: "POST" });
}

export async function uploadDocument(file: File) {
  const body = new FormData();
  body.append("file", file);
  const response = await fetch(toUrl("/api/upload"), {
    method: "POST",
    body,
  });
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(detail || `Upload failed with ${response.status}`);
  }
  return (await response.json()) as IngestResponse;
}

export async function getAuditLog() {
  return requestJson<AuditEvent[]>("/api/audit");
}

export async function decideTool(proposalId: string, approved: boolean) {
  return requestJson<ToolDecisionResponse>("/api/tools/execute", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ proposal_id: proposalId, approved }),
  });
}

export async function streamChat(
  question: string,
  handlers: EventHandlers,
  signal?: AbortSignal,
) {
  const response = await fetch(toUrl("/api/chat"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question }),
    signal,
  });

  if (!response.ok || !response.body) {
    const detail = await response.text();
    throw new Error(detail || "Streaming response was unavailable");
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) {
      break;
    }
    buffer += decoder.decode(value, { stream: true });

    let boundary = buffer.indexOf("\n\n");
    while (boundary !== -1) {
      const rawBlock = buffer.slice(0, boundary).trim();
      buffer = buffer.slice(boundary + 2);
      if (rawBlock) {
        const parsed = parseEventBlock(rawBlock);
        if (parsed) {
          switch (parsed.eventName) {
            case "meta":
              handlers.onMeta(parsed.payload as ChatMeta);
              break;
            case "token":
              handlers.onToken(parsed.payload as string);
              break;
            case "error": {
              const payload = parsed.payload as { message?: string };
              handlers.onError(payload.message ?? "The request failed safely.");
              break;
            }
            case "done":
              handlers.onDone(parsed.payload as { audit_id?: string });
              break;
            default:
              break;
          }
        }
      }
      boundary = buffer.indexOf("\n\n");
    }
  }
}
