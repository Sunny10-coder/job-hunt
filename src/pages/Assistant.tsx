import { AlertTriangle, Bot, CheckCircle2, Send, Sparkles, XCircle } from "lucide-react";
import * as React from "react";
import { MessageInspector } from "@/components/MessageInspector";
import { PageHeader } from "@/components/layout/PageHeader";
import { Badge, Button, EmptyState, ErrorState, Field, Panel, Select, Spinner, Textarea } from "@/components/ui/primitives";
import { post } from "@/lib/api";
import { dateTime, num } from "@/lib/format";
import { useApi } from "@/hooks/useApi";
import { useCase } from "@/hooks/useCaseContext";
import { useApp } from "@/stores/app";
import type { AiAnswer, Conversation } from "@/types";

interface AiStatus {
  ok: boolean;
  enabled: boolean;
  provider: string | null;
  models: string[];
  configured_model?: string;
  error?: string;
  hint?: string;
  external?: boolean;
  requires_disclosure?: boolean;
}

const SUGGESTIONS = [
  "Summarise this conversation and the main themes.",
  "Which topics were discussed most frequently?",
  "Show the days with the highest message activity.",
  "Compare communication frequency between two months.",
  "Find messages that mention travel or meeting plans.",
  "Identify the main changes in conversation topics.",
];

export function AssistantPage() {
  const { caseId } = useCase();
  const toast = useApp((state) => state.toast);
  const [question, setQuestion] = React.useState("");
  const [conversationId, setConversationId] = React.useState("");
  const [busy, setBusy] = React.useState(false);
  const [answers, setAnswers] = React.useState<AiAnswer[]>([]);
  const [inspect, setInspect] = React.useState<string | null>(null);
  const [error, setError] = React.useState<string | null>(null);

  const statusApi = useApi<AiStatus>("/api/ai/status");
  const conversationsApi = useApi<Conversation[]>(caseId ? `/api/cases/${caseId}/conversations` : null, [caseId]);
  const settingsApi = useApi<{ ai_model: string; ai_provider: string; ai_enabled: boolean }>("/api/settings");

  const ask = async (text?: string) => {
    const prompt = (text ?? question).trim();
    if (!prompt) return;
    setBusy(true);
    setError(null);
    try {
      const answer = await post<AiAnswer>(`/api/cases/${caseId}/ai/ask`, {
        question: prompt,
        conversation_id: conversationId || undefined,
      });
      setAnswers((current) => [answer, ...current]);
      setQuestion("");
      if (answer.status === "unavailable") {
        toast({ title: "No model answered", description: "Evidence and statistics were still retrieved.", tone: "info" });
      }
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex h-full min-h-0 flex-col">
      <PageHeader
        title="AI investigation assistant"
        description="Evidence-grounded questions over this case. Answers separate observed evidence, computed statistics and AI interpretation; every citation resolves to a stored message."
        badges={
          statusApi.data ? (
            <Badge tone={statusApi.data.ok ? "teal" : statusApi.data.enabled ? "amber" : "muted"}>
              {statusApi.data.ok ? `${statusApi.data.provider}` : statusApi.data.enabled ? "provider offline" : "AI disabled"}
            </Badge>
          ) : null
        }
        actions={
          <Field label="Scope" className="w-56">
            <Select value={conversationId} onChange={(event) => setConversationId(event.target.value)}>
              <option value="">Whole case</option>
              {(conversationsApi.data ?? []).map((conversation) => (
                <option key={conversation.id} value={conversation.id}>
                  {conversation.title}
                </option>
              ))}
            </Select>
          </Field>
        }
      />

      <div className="grid min-h-0 flex-1 grid-cols-[minmax(0,1fr)_320px]">
        <div className="flex min-h-0 flex-col">
          <div className="min-h-0 flex-1 overflow-y-auto p-4 scroll-thin">
            {answers.length === 0 ? (
              <Panel>
                <EmptyState
                  icon={<Bot className="h-8 w-8" />}
                  title="Ask a question about this evidence"
                  description="The assistant retrieves matching records with full-text (and optional local vector) search, then answers only from that context. It cannot modify evidence."
                />
                <div className="mt-2 grid gap-1.5 sm:grid-cols-2">
                  {SUGGESTIONS.map((suggestion) => (
                    <button
                      key={suggestion}
                      onClick={() => void ask(suggestion)}
                      className="surface-muted px-2.5 py-2 text-left text-[11.5px] text-muted transition hover:border-accent/40 hover:text-ink"
                    >
                      <Sparkles className="mr-1 inline h-3 w-3 text-accent" />
                      {suggestion}
                    </button>
                  ))}
                </div>
              </Panel>
            ) : null}

            <div className="space-y-3">
              {answers.map((answer) => (
                <article key={answer.id} className="space-y-2">
                  <div className="flex justify-end">
                    <div className="bubble-out max-w-[80%] px-3 py-2">
                      <p dir="auto" className="text-[12.5px] text-ink">{answer.question}</p>
                    </div>
                  </div>
                  <Panel
                    title={
                      <span className="flex items-center gap-1.5">
                        <Bot className="h-3.5 w-3.5 text-accent" />
                        {answer.provider} · {answer.model || "no model"}
                      </span>
                    }
                    subtitle={`${answer.duration_ms} ms · ${num(answer.observed.retrieved)} evidence excerpts`}
                    actions={
                      <Badge tone={answer.status === "ok" ? "teal" : answer.status === "disabled" ? "muted" : "amber"}>
                        {answer.status}
                      </Badge>
                    }
                  >
                    {answer.error ? (
                      <p className="mb-2 rounded-lg border border-amber/30 bg-amber/8 p-2 text-[11px] text-amber">{answer.error}</p>
                    ) : null}

                    {answer.answer ? (
                      <p dir="auto" className="prose-chat whitespace-pre-wrap text-[12.5px] leading-relaxed text-ink">{answer.answer}</p>
                    ) : null}

                    {answer.invalid_citations.length > 0 ? (
                      <p className="mt-2 flex items-start gap-1.5 rounded-lg border border-danger/30 bg-danger/8 p-2 text-[10.5px] text-danger">
                        <XCircle className="mt-0.5 h-3 w-3 shrink-0" />
                        The model referenced {answer.invalid_citations.join(", ")} which do not map to retrieved
                        records; those markers were replaced.
                      </p>
                    ) : null}

                    {answer.citations.length > 0 ? (
                      <div className="mt-3">
                        <p className="section-title mb-1">Verified citations</p>
                        <div className="space-y-1">
                          {answer.citations.map((citation) => (
                            <button
                              key={citation.message_id}
                              onClick={() => setInspect(citation.message_id)}
                              className="surface-muted w-full px-2.5 py-1.5 text-left transition hover:border-accent/40"
                            >
                              <div className="flex items-center justify-between gap-2">
                                <span dir="auto" className="text-[11px] text-accent">
                                  {citation.marker ?? "[M]"} {citation.sender ?? ""}
                                </span>
                                <span className="text-[10px] text-muted">
                                  {citation.sent_at_utc ? dateTime(citation.sent_at_utc) : ""} · score {citation.score}
                                </span>
                              </div>
                              <p dir="auto" className="mt-0.5 line-clamp-2 text-[11.5px] text-ink">{citation.snippet}</p>
                            </button>
                          ))}
                        </div>
                      </div>
                    ) : null}

                    {answer.citations.length === 0 && (answer.observed.records?.length ?? 0) > 0 ? (
                      <div className="mt-3">
                        <p className="section-title mb-1">Retrieved excerpts (no claims to cite)</p>
                        <div className="space-y-1">
                          {answer.observed.records?.slice(0, 6).map((record) => (
                            <button
                              key={record.message_id}
                              onClick={() => setInspect(record.message_id)}
                              className="surface-muted w-full px-2.5 py-1.5 text-left transition hover:border-accent/40"
                            >
                              <div className="flex items-center justify-between gap-2">
                                <span dir="auto" className="text-[11px] text-accent">{record.sender ?? ""}</span>
                                <span className="text-[10px] text-muted">
                                  {record.sent_at_utc ? dateTime(record.sent_at_utc) : ""}
                                </span>
                              </div>
                              <p dir="auto" className="mt-0.5 line-clamp-2 text-[11.5px] text-ink">{record.snippet}</p>
                            </button>
                          ))}
                        </div>
                      </div>
                    ) : null}

                    <div className="mt-3 grid gap-2 sm:grid-cols-2">
                      <div className="rounded-lg border border-line bg-elevated/40 p-2">
                        <p className="text-[10px] uppercase tracking-[0.07em] text-muted">Computed statistics</p>
                        <p className="mt-1 text-[11px] text-ink">
                          {num(Number((answer.observed.stats.overview as { real_messages?: number })?.real_messages ?? 0))} messages ·{" "}
                          {num(Number((answer.observed.stats.overview as { active_days?: number })?.active_days ?? 0))} active days
                        </p>
                        <p className="text-[10.5px] text-muted">
                          median reply{" "}
                          {String(((answer.observed.stats.response as { median_minutes?: number })?.median_minutes) ?? "—")} min
                        </p>
                      </div>
                      <div className="rounded-lg border border-amber/25 bg-amber/6 p-2">
                        <p className="text-[10px] uppercase tracking-[0.07em] text-amber">Interpretation</p>
                        <p className="mt-1 text-[10.5px] leading-relaxed text-muted">{answer.disclosure}</p>
                      </div>
                    </div>
                  </Panel>
                </article>
              ))}
            </div>

            {error ? <ErrorState error={error} /> : null}
            {busy ? <Spinner label="Retrieving evidence and asking the local model…" /> : null}
          </div>

          <div className="border-t border-line bg-panel/60 p-3">
            <div className="flex items-end gap-2">
              <Textarea
                value={question}
                onChange={(event) => setQuestion(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === "Enter" && !event.shiftKey) {
                    event.preventDefault();
                    void ask();
                  }
                }}
                placeholder="Ask about this evidence… (Enter to send, Shift+Enter for a new line)"
                className="min-h-[52px]"
              />
              <Button variant="primary" loading={busy} onClick={() => void ask()}>
                <Send className="h-3.5 w-3.5" /> Ask
              </Button>
            </div>
            <p className="mt-1 text-[10px] text-muted">
              Model: {settingsApi.data?.ai_model ?? "not configured"} · provider {settingsApi.data?.ai_provider ?? "ollama"}.
              Imported chat text is treated as untrusted data and cannot issue instructions.
            </p>
          </div>
        </div>

        <aside className="space-y-3 overflow-y-auto border-l border-line bg-panel/40 p-3 scroll-thin">
          <Panel title="Provider status" dense>
            {statusApi.loading ? <Spinner /> : null}
            {statusApi.data ? (
              <div className="space-y-1.5 p-2 text-[11px]">
                <p className="flex items-center gap-1.5 text-ink">
                  {statusApi.data.ok ? <CheckCircle2 className="h-3.5 w-3.5 text-teal" /> : <AlertTriangle className="h-3.5 w-3.5 text-amber" />}
                  {statusApi.data.ok ? "Model endpoint reachable" : "Model endpoint unavailable"}
                </p>
                <p className="text-muted">{statusApi.data.provider ?? "—"}</p>
                {statusApi.data.models.length > 0 ? (
                  <div className="flex flex-wrap gap-1">
                    {statusApi.data.models.slice(0, 8).map((model) => (
                      <span key={model} className="chip">{model}</span>
                    ))}
                  </div>
                ) : null}
                {statusApi.data.error ? <p className="text-amber">{statusApi.data.error}</p> : null}
                {statusApi.data.hint ? <p className="text-muted">{statusApi.data.hint}</p> : null}
              </div>
            ) : null}
          </Panel>

          <Panel title="Grounding rules" dense>
            <ul className="space-y-1.5 p-2 text-[10.5px] leading-relaxed text-muted">
              <li>• Answers use only retrieved excerpts and computed statistics.</li>
              <li>• Every factual claim must cite a [M#] excerpt; invalid markers are removed.</li>
              <li>• Evidence text is sanitised so chat content cannot become instructions.</li>
              <li>• External providers stay disabled until you enable them and confirm disclosure.</li>
            </ul>
          </Panel>
        </aside>
      </div>

      <MessageInspector caseId={caseId} messageId={inspect} open={Boolean(inspect)} onClose={() => setInspect(null)} />
    </div>
  );
}
