import { BookMarked, Filter, Save, Search as SearchIcon } from "lucide-react";
import * as React from "react";
import { useSearchParams } from "react-router-dom";
import { MessageInspector } from "@/components/MessageInspector";
import { PageHeader } from "@/components/layout/PageHeader";
import { Badge, Button, Checkbox, EmptyState, ErrorState, Field, Input, Panel, Select, Spinner, Tabs } from "@/components/ui/primitives";
import { post } from "@/lib/api";
import { dateTime, num, splitHighlights } from "@/lib/format";
import { useApi } from "@/hooks/useApi";
import { useCase } from "@/hooks/useCaseContext";
import { useApp } from "@/stores/app";
import type { Contact, Conversation, SearchResult } from "@/types";

type Mode = "fts" | "exact" | "regex";

export function SearchPage() {
  const { caseId } = useCase();
  const [params] = useSearchParams();
  const toast = useApp((state) => state.toast);
  const [query, setQuery] = React.useState(params.get("q") ?? "");
  const [mode, setMode] = React.useState<Mode>("fts");
  const [conversationId, setConversationId] = React.useState("");
  const [senderId, setSenderId] = React.useState("");
  const [from, setFrom] = React.useState("");
  const [to, setTo] = React.useState("");
  const [mediaOnly, setMediaOnly] = React.useState(false);
  const [deletedOnly, setDeletedOnly] = React.useState(false);
  const [editedOnly, setEditedOnly] = React.useState(false);
  const [bookmarkedOnly, setBookmarkedOnly] = React.useState(false);
  const [tag, setTag] = React.useState("");
  const [results, setResults] = React.useState<{ total: number; results: SearchResult[]; took_ms: number; notes: string[] } | null>(null);
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [inspect, setInspect] = React.useState<string | null>(null);
  const [showFilters, setShowFilters] = React.useState(true);

  const conversationsApi = useApi<Conversation[]>(caseId ? `/api/cases/${caseId}/conversations` : null, [caseId]);
  const contactsApi = useApi<Contact[]>(caseId ? `/api/cases/${caseId}/contacts` : null, [caseId]);
  const savedApi = useApi<{ id: string; name: string; created_at: string }[]>(caseId ? `/api/cases/${caseId}/searches` : null, [caseId]);
  const tagsApi = useApi<{ tag: string; count: number }[]>(caseId ? `/api/cases/${caseId}/tags` : null, [caseId]);

  const run = React.useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const payload = await post<{ total: number; results: SearchResult[]; took_ms: number; notes: string[] }>(
        `/api/cases/${caseId}/search`,
        {
          q: query,
          mode,
          conversation_ids: conversationId ? [conversationId] : [],
          sender_ids: senderId ? [senderId] : [],
          date_from: from || undefined,
          date_to: to || undefined,
          media_type: mediaOnly ? "any" : undefined,
          is_deleted: deletedOnly ? true : undefined,
          is_edited: editedOnly ? true : undefined,
          bookmarked: bookmarkedOnly || undefined,
          tag: tag || undefined,
          limit: 100,
        },
      );
      setResults(payload);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  }, [caseId, query, mode, conversationId, senderId, from, to, mediaOnly, deletedOnly, editedOnly, bookmarkedOnly, tag]);

  React.useEffect(() => {
    if (params.get("q")) void run();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="flex h-full min-h-0 flex-col">
      <PageHeader
        title="Advanced search"
        description="SQLite FTS5 full-text search with structured filters, plus exact and bounded regex modes. Every result links to its source record."
        badges={results ? <Badge tone="accent">{num(results.total)} matches · {results.took_ms} ms</Badge> : null}
        actions={
          <Button variant="ghost" size="sm" onClick={() => setShowFilters(!showFilters)}>
            <Filter className="h-3.5 w-3.5" /> {showFilters ? "Hide filters" : "Show filters"}
          </Button>
        }
      />

      <div className="border-b border-line bg-panel/50 px-4 py-2">
        <div className="flex flex-wrap items-end gap-2">
          <Field label="Query" className="min-w-[280px] flex-1">
            <div className="relative">
              <SearchIcon className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted" />
              <Input
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                onKeyDown={(event) => event.key === "Enter" && void run()}
                placeholder='hotel AND "boat tour" · word* prefix · plain keywords'
                className="pl-8"
              />
            </div>
          </Field>
          <Field label="Mode" className="w-40">
            <Select value={mode} onChange={(event) => setMode(event.target.value as Mode)}>
              <option value="fts">Full text (FTS5)</option>
              <option value="exact">Exact phrase</option>
              <option value="regex">Regular expression</option>
            </Select>
          </Field>
          <Button variant="primary" loading={loading} onClick={() => void run()}>
            Search
          </Button>
          <Button
            variant="ghost"
            onClick={async () => {
              const name = window.prompt("Save this search as:", query || "filtered search");
              if (!name) return;
              await post(`/api/cases/${caseId}/searches`, {
                name,
                query: { q: query, mode, conversation_ids: conversationId ? [conversationId] : [], sender_ids: senderId ? [senderId] : [] },
              });
              savedApi.reload();
              toast({ title: "Search saved", tone: "success" });
            }}
          >
            <Save className="h-3.5 w-3.5" /> Save
          </Button>
        </div>

        {showFilters ? (
          <div className="mt-2 grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
            <Field label="Conversation">
              <Select value={conversationId} onChange={(event) => setConversationId(event.target.value)}>
                <option value="">All</option>
                {(conversationsApi.data ?? []).map((conversation) => (
                  <option key={conversation.id} value={conversation.id}>{conversation.title}</option>
                ))}
              </Select>
            </Field>
            <Field label="Sender">
              <Select value={senderId} onChange={(event) => setSenderId(event.target.value)}>
                <option value="">Anyone</option>
                {(contactsApi.data ?? []).map((contact) => (
                  <option key={contact.id} value={contact.id}>{contact.display_name}</option>
                ))}
              </Select>
            </Field>
            <Field label="From">
              <input type="date" value={from} onChange={(event) => setFrom(event.target.value)} className="field text-[12px]" />
            </Field>
            <Field label="To">
              <input type="date" value={to} onChange={(event) => setTo(event.target.value)} className="field text-[12px]" />
            </Field>
            <Field label="Tag">
              <Select value={tag} onChange={(event) => setTag(event.target.value)}>
                <option value="">Any tag</option>
                {(tagsApi.data ?? []).map((item) => (
                  <option key={item.tag} value={item.tag}>{item.tag} ({item.count})</option>
                ))}
              </Select>
            </Field>
            <div className="flex flex-wrap items-center gap-3 sm:col-span-2 lg:col-span-3">
              <Checkbox checked={mediaOnly} onChange={setMediaOnly} label={<span className="text-[11.5px]">media only</span>} />
              <Checkbox checked={deletedOnly} onChange={setDeletedOnly} label={<span className="text-[11.5px]">deleted markers</span>} />
              <Checkbox checked={editedOnly} onChange={setEditedOnly} label={<span className="text-[11.5px]">edited markers</span>} />
              <Checkbox checked={bookmarkedOnly} onChange={setBookmarkedOnly} label={<span className="text-[11.5px]">bookmarked</span>} />
            </div>
          </div>
        ) : null}
      </div>

      <div className="grid min-h-0 flex-1 grid-cols-[minmax(0,1fr)_250px]">
        <div className="min-h-0 overflow-y-auto p-4 scroll-thin">
          {loading ? <Spinner label="Searching…" /> : null}
          {error ? <ErrorState error={error} onRetry={() => void run()} /> : null}
          {!loading && !results ? (
            <EmptyState icon={<SearchIcon className="h-7 w-7" />} title="Run a search" description="Use quotes for phrases, AND / OR / NOT for boolean logic, and a trailing * for prefix matching." />
          ) : null}
          {results && results.results.length === 0 ? (
            <EmptyState title="No matches" description="Try a broader query or remove a filter." />
          ) : null}
          <div className="space-y-1.5">
            {(results?.results ?? []).map((result) => (
              <button
                key={result.id}
                onClick={() => setInspect(result.id)}
                className="surface w-full px-3 py-2 text-left transition hover:border-accent/40"
              >
                <div className="flex flex-wrap items-center gap-1.5">
                  <Badge tone="accent">{result.sender_raw}</Badge>
                  <span dir="auto" className="text-[10.5px] text-muted">{result.conversation}</span>
                  <span className="text-[10.5px] text-muted">· {dateTime(result.sent_at_utc)}</span>
                  {result.has_media ? <Badge tone="teal">media</Badge> : null}
                  {result.is_deleted ? <Badge tone="danger">deleted</Badge> : null}
                  {result.is_edited ? <Badge tone="amber">edited</Badge> : null}
                  {result.parse_confidence < 0.8 ? <Badge tone="amber">low confidence</Badge> : null}
                </div>
                <p dir="auto" className="mt-1 text-[12.5px] leading-relaxed text-ink">
                  {splitHighlights(result.snippet).map((part, index) =>
                    part.hit ? (
                      <mark key={index}>{part.text}</mark>
                    ) : (
                      <span key={index}>{part.text}</span>
                    ),
                  )}
                </p>
                <p className="mono mt-1 text-[10px] text-muted">{result.source_ref}</p>
              </button>
            ))}
          </div>
          {results?.notes?.length ? (
            <p className="mt-3 mono text-[10px] text-muted">{results.notes.join(" · ")}</p>
          ) : null}
        </div>

        <aside className="space-y-3 overflow-y-auto border-l border-line bg-panel/40 p-3 scroll-thin">
          <Panel title="Saved searches" dense>
            <div className="divide-y divide-line/60">
              {(savedApi.data ?? []).map((saved) => (
                <div key={saved.id} className="flex items-center justify-between gap-2 px-3 py-1.5">
                  <span className="truncate text-[11.5px] text-ink">{saved.name}</span>
                  <BookMarked className="h-3 w-3 text-muted" />
                </div>
              ))}
              {(savedApi.data ?? []).length === 0 ? <p className="p-3 text-[11px] text-muted">No saved searches yet.</p> : null}
            </div>
          </Panel>
          <Panel title="Query syntax" dense>
            <ul className="space-y-1 p-2 text-[10.5px] leading-relaxed text-muted">
              <li><span className="mono text-ink">"exact phrase"</span> phrase match</li>
              <li><span className="mono text-ink">hotel AND travel</span> both terms</li>
              <li><span className="mono text-ink">hotel OR station</span> either term</li>
              <li><span className="mono text-ink">tick*</span> prefix match</li>
              <li><span className="mono text-ink">NOT hotel</span> exclusion</li>
              <li>Regex mode is capped at 300 characters and scans the newest 200k matching rows.</li>
            </ul>
          </Panel>
          <Panel title="Export" dense>
            <div className="space-y-1.5 p-2">
              <Button
                size="sm"
                variant="ghost"
                className="w-full"
                onClick={async () => {
                  const result = await post<{ path: string; rows: number }>(`/api/cases/${caseId}/export/messages`, {
                    format: "csv",
                    conversation_id: conversationId || undefined,
                    contact_id: senderId || undefined,
                    date_from: from || undefined,
                    date_to: to || undefined,
                  });
                  toast({ title: `Exported ${result.rows} records`, description: result.path, tone: "success" });
                }}
              >
                Export filtered messages (CSV)
              </Button>
              <p className="text-[10px] text-muted">Exports are written to the case export folder and hashed.</p>
            </div>
          </Panel>
          <Tabs value={mode} onChange={(value) => setMode(value)} tabs={[{ value: "fts", label: "FTS" }, { value: "exact", label: "Exact" }, { value: "regex", label: "Regex" }]} />
        </aside>
      </div>

      <MessageInspector caseId={caseId} messageId={inspect} open={Boolean(inspect)} onClose={() => setInspect(null)} />
    </div>
  );
}
