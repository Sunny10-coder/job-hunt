import { Search } from "lucide-react";
import * as React from "react";
import { MessageInspector } from "@/components/MessageInspector";
import { PageHeader } from "@/components/layout/PageHeader";
import { Badge, Button, Checkbox, EmptyState, ErrorState, Field, Select, Spinner } from "@/components/ui/primitives";
import { useApi } from "@/hooks/useApi";
import { useCase } from "@/hooks/useCaseContext";
import { dateTime, dateOnly, num, truncate } from "@/lib/format";
import type { Conversation, TimelineEvent } from "@/types";

const KINDS = [
  { value: "message", label: "Messages" },
  { value: "group", label: "Group events" },
  { value: "import", label: "Evidence imports" },
  { value: "annotation", label: "Book / notes" },
];

export function TimelinePage() {
  const { caseId } = useCase();
  const [kinds, setKinds] = React.useState<string[]>(["message", "group", "import", "annotation"]);
  const [conversationId, setConversationId] = React.useState("");
  const [from, setFrom] = React.useState("");
  const [to, setTo] = React.useState("");
  const [limit, setLimit] = React.useState(400);
  const [inspect, setInspect] = React.useState<string | null>(null);

  const conversationsApi = useApi<Conversation[]>(caseId ? `/api/cases/${caseId}/conversations` : null, [caseId]);

  const query = new URLSearchParams();
  if (kinds.length) query.set("kinds", kinds.join(","));
  if (conversationId) query.set("conversation_id", conversationId);
  if (from) query.set("from", from);
  if (to) query.set("to", to);
  query.set("limit", String(limit));

  const timelineApi = useApi<{ events: TimelineEvent[]; total: number }>(
    caseId ? `/api/cases/${caseId}/timeline?${query.toString()}` : null,
    [caseId, kinds.join(","), conversationId, from, to, limit],
  );

  const grouped = React.useMemo(() => {
    const map = new Map<string, TimelineEvent[]>();
    for (const event of timelineApi.data?.events ?? []) {
      const day = dateOnly(event.at);
      map.set(day, [...(map.get(day) ?? []), event]);
    }
    return Array.from(map.entries());
  }, [timelineApi.data]);

  return (
    <div className="flex h-full min-h-0 flex-col">
      <PageHeader
        title="Timeline reconstruction"
        description="Unified chronological view of messages, group events, imports and your annotations. Times are normalised to UTC; DST-ambiguous timestamps are flagged on the record."
        badges={timelineApi.data ? <Badge tone="accent">{num(timelineApi.data.events.length)} events</Badge> : null}
        actions={
          <Button variant="ghost" size="sm" onClick={() => setLimit((value) => Math.min(2000, value + 400))}>
            Load more
          </Button>
        }
      />
      <div className="flex flex-wrap items-end gap-2 border-b border-line bg-panel/50 px-4 py-2">
        {KINDS.map((kind) => (
          <Checkbox
            key={kind.value}
            checked={kinds.includes(kind.value)}
            onChange={(value) => setKinds((current) => (value ? [...current, kind.value] : current.filter((item) => item !== kind.value)))}
            label={<span className="text-[11.5px]">{kind.label}</span>}
          />
        ))}
        <Field label="Conversation" className="w-56">
          <Select value={conversationId} onChange={(event) => setConversationId(event.target.value)}>
            <option value="">All</option>
            {(conversationsApi.data ?? []).map((conversation) => (
              <option key={conversation.id} value={conversation.id}>
                {conversation.title}
              </option>
            ))}
          </Select>
        </Field>
        <Field label="From" className="w-36">
          <input type="date" value={from} onChange={(event) => setFrom(event.target.value)} className="field text-[12px]" />
        </Field>
        <Field label="To" className="w-36">
          <input type="date" value={to} onChange={(event) => setTo(event.target.value)} className="field text-[12px]" />
        </Field>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto px-4 py-3 scroll-thin">
        {timelineApi.loading && !timelineApi.data ? <Spinner label="Building timeline…" /> : null}
        {timelineApi.error ? <ErrorState error={timelineApi.error} onRetry={timelineApi.reload} /> : null}
        {grouped.length === 0 && !timelineApi.loading ? (
          <EmptyState icon={<Search className="h-7 w-7" />} title="No events in this range" />
        ) : null}
        <div className="relative mx-auto max-w-4xl">
          <div className="absolute bottom-0 left-[86px] top-2 w-px bg-line" />
          {grouped.map(([day, events]) => (
            <section key={day} className="mb-4">
              <div className="mb-1.5 flex items-center gap-2">
                <span className="w-[76px] text-right text-[10.5px] font-medium text-muted">{day}</span>
                <span className="h-2 w-2 rounded-full border border-accent/60 bg-accent/30" />
                <span className="text-[10.5px] text-muted">{events.length} events</span>
              </div>
              <div className="space-y-1">
                {events.map((event) => (
                  <div key={`${event.kind}-${event.id}`} className="flex gap-3">
                    <div className="w-[76px] shrink-0 pt-1 text-right">
                      <span className="mono text-[10px] text-muted">{event.at.slice(11, 16)}</span>
                    </div>
                    <span
                      className={`mt-1.5 h-2 w-2 shrink-0 rounded-full ${
                        event.kind === "message"
                          ? "bg-accent"
                          : event.kind === "group_event"
                            ? "bg-teal"
                            : event.kind === "import"
                              ? "bg-amber"
                              : "bg-[#a78bfa]"
                      }`}
                    />
                    <button
                      onClick={() => event.message_id && setInspect(event.message_id)}
                      className={`min-w-0 flex-1 rounded-lg border border-line bg-panel/60 px-2.5 py-1.5 text-left transition hover:border-accent/35 ${
                        event.message_id ? "cursor-pointer" : "cursor-default"
                      }`}
                    >
                      <div className="flex items-center justify-between gap-2">
                        <span dir="auto" className="truncate text-[11.5px] text-ink">{event.title}</span>
                        <Badge tone={event.kind === "import" ? "amber" : event.kind === "group_event" ? "teal" : "muted"}>
                          {event.kind.replace("_", " ")}
                        </Badge>
                      </div>
                      {event.detail ? (
                        <p dir="auto" className="mt-0.5 line-clamp-2 text-[10.5px] leading-snug text-muted">
                          {truncate(event.detail, 180)}
                        </p>
                      ) : null}
                    </button>
                  </div>
                ))}
              </div>
            </section>
          ))}
        </div>
      </div>

      <MessageInspector caseId={caseId} messageId={inspect} open={Boolean(inspect)} onClose={() => setInspect(null)} />
      {timelineApi.data ? (
        <footer className="border-t border-line px-4 py-1.5 text-[10.5px] text-muted">
          Showing {num(timelineApi.data.events.length)} of {num(timelineApi.data.total)} collected events · newest first per day, UTC
          · generated {dateTime(new Date().toISOString())}
        </footer>
      ) : null}
    </div>
  );
}
