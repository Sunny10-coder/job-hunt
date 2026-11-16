import { ArrowDown, ArrowUp, Bookmark, MessageSquare, Paperclip, Search, ShieldQuestion } from "lucide-react";
import * as React from "react";
import { useSearchParams } from "react-router-dom";
import { MessageInspector } from "@/components/MessageInspector";
import { PageHeader } from "@/components/layout/PageHeader";
import { Badge, Button, EmptyState, ErrorState, Input, Spinner } from "@/components/ui/primitives";
import { get } from "@/lib/api";
import { dateOnly, dateTime, num, timeOnly, truncate } from "@/lib/format";
import { useCase } from "@/hooks/useCaseContext";
import { useApi } from "@/hooks/useApi";
import type { Conversation, Message } from "@/types";

const PAGE = 120;

export function Explorer() {
  const { caseId } = useCase();
  const [params, setParams] = useSearchParams();
  const selected = params.get("c");
  const focusMessage = params.get("m");
  const highlight = params.get("q") ?? "";
  const [filter, setFilter] = React.useState("");
  const [messages, setMessages] = React.useState<Message[]>([]);
  const [loadingOlder, setLoadingOlder] = React.useState(false);
  const [inspect, setInspect] = React.useState<string | null>(focusMessage);
  const [onlyMedia, setOnlyMedia] = React.useState(false);

  const conversationsApi = useApi<Conversation[]>(caseId ? `/api/cases/${caseId}/conversations` : null, [caseId]);
  const conversations = conversationsApi.data ?? [];

  React.useEffect(() => {
    if (!selected && conversations.length > 0) {
      const next = new URLSearchParams(params);
      next.set("c", conversations[0].id);
      setParams(next, { replace: true });
    }
  }, [conversations, selected, params, setParams]);

  const conversationApi = useApi<{ messages: Message[]; total: number }>(
    caseId && selected ? `/api/cases/${caseId}/conversations/${selected}/messages?limit=${PAGE}` : null,
    [caseId, selected],
  );

  React.useEffect(() => {
    if (conversationApi.data) setMessages(conversationApi.data.messages);
  }, [conversationApi.data]);

  React.useEffect(() => {
    if (focusMessage) setInspect(focusMessage);
  }, [focusMessage]);

  const conversation = conversations.find((item) => item.id === selected);
  const visible = React.useMemo(() => {
    const list = onlyMedia ? messages.filter((message) => message.has_media) : messages;
    return list;
  }, [messages, onlyMedia]);

  const loadOlder = async () => {
    if (!selected || messages.length === 0) return;
    setLoadingOlder(true);
    try {
      const anchor = messages[0].id;
      const payload = await get<{ messages: Message[] }>(
        `/api/cases/${caseId}/conversations/${selected}/messages?limit=${PAGE}&anchor=${anchor}&direction=backward`,
      );
      const known = new Set(messages.map((message) => message.id));
      const older = payload.messages.filter((message) => !known.has(message.id));
      setMessages([...older, ...messages]);
    } finally {
      setLoadingOlder(false);
    }
  };

  const loadNewer = async () => {
    if (!selected || messages.length === 0) return;
    setLoadingOlder(true);
    try {
      const anchor = messages[messages.length - 1].id;
      const payload = await get<{ messages: Message[] }>(
        `/api/cases/${caseId}/conversations/${selected}/messages?limit=${PAGE}&anchor=${anchor}&direction=forward`,
      );
      const known = new Set(messages.map((message) => message.id));
      const newer = payload.messages.filter((message) => !known.has(message.id));
      setMessages([...messages, ...newer]);
    } finally {
      setLoadingOlder(false);
    }
  };

  const toggleBookmark = async (message: Message) => {
    const { post, del } = await import("@/lib/api");
    if (message.bookmarked) await del(`/api/cases/${caseId}/bookmarks/${message.id}`);
    else await post(`/api/cases/${caseId}/bookmarks`, { message_id: message.id, label: "key evidence" });
    setMessages(messages.map((item) => (item.id === message.id ? { ...item, bookmarked: !item.bookmarked } : item)));
  };

  const filteredConversations = conversations.filter((item) =>
    item.title.toLowerCase().includes(filter.toLowerCase()),
  );

  return (
    <div className="flex h-full min-h-0 flex-col">
      <PageHeader
        title="Conversation explorer"
        description="Read imported conversations with original timestamps, media placeholders and system events. Delivery/read receipts are never fabricated: they are absent from exports."
        badges={
          conversation ? (
            <>
              <Badge tone={conversation.kind === "group" ? "teal" : "accent"}>{conversation.kind}</Badge>
              <Badge>{num(conversation.message_count)} messages</Badge>
            </>
          ) : null
        }
        actions={
          <>
            <Button variant={onlyMedia ? "primary" : "ghost"} size="sm" onClick={() => setOnlyMedia(!onlyMedia)}>
              <Paperclip className="h-3.5 w-3.5" /> Media only
            </Button>
            <Button variant="ghost" size="sm" onClick={() => void loadOlder()} loading={loadingOlder}>
              <ArrowUp className="h-3.5 w-3.5" /> Older
            </Button>
            <Button variant="ghost" size="sm" onClick={() => void loadNewer()} loading={loadingOlder}>
              <ArrowDown className="h-3.5 w-3.5" /> Newer
            </Button>
          </>
        }
      />

      <div className="grid min-h-0 flex-1 grid-cols-[290px_minmax(0,1fr)]">
        <aside className="flex min-h-0 flex-col border-r border-line bg-panel/40">
          <div className="border-b border-line p-2">
            <div className="relative">
              <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted" />
              <Input
                value={filter}
                onChange={(event) => setFilter(event.target.value)}
                placeholder="Filter conversations"
                className="h-8 pl-8 text-[12px]"
              />
            </div>
          </div>
          <div className="min-h-0 flex-1 overflow-y-auto scroll-thin">
            {conversationsApi.loading ? <Spinner /> : null}
            {conversationsApi.error ? <ErrorState error={conversationsApi.error} onRetry={conversationsApi.reload} /> : null}
            {filteredConversations.map((item) => (
              <button
                key={item.id}
                onClick={() => {
                  const next = new URLSearchParams(params);
                  next.set("c", item.id);
                  next.delete("m");
                  setParams(next);
                }}
                className={`w-full border-b border-line/50 px-3 py-2.5 text-left transition hover:bg-elevated/60 ${
                  selected === item.id ? "bg-elevated" : ""
                }`}
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="truncate text-[12.5px] font-medium text-ink">{item.title}</span>
                  {item.kind === "group" ? <Badge tone="teal">group</Badge> : null}
                </div>
                <p className="mt-0.5 truncate text-[11px] text-muted">
                  {item.last_sender ? `${item.last_sender}: ` : ""}
                  {truncate(item.last_message ?? "", 54) || "—"}
                </p>
                <p className="mt-0.5 text-[10px] text-muted/80">
                  {num(item.message_count)} msgs · {num(item.media_count)} media · {dateOnly(item.last_at)}
                </p>
              </button>
            ))}
            {filteredConversations.length === 0 && !conversationsApi.loading ? (
              <EmptyState title="No conversations" description="Import evidence to populate this list." />
            ) : null}
          </div>
        </aside>

        <section className="flex min-h-0 flex-col bg-bg">
          <header className="flex items-center justify-between border-b border-line px-4 py-2">
            <div>
              <p className="text-[12.5px] font-semibold text-ink">{conversation?.title ?? "Select a conversation"}</p>
              <p className="text-[10.5px] text-muted">
                {conversation
                  ? `${num(conversation.message_count)} messages · ${num(conversation.media_count)} media · ${dateTime(conversation.first_at)} → ${dateTime(conversation.last_at)}`
                  : "Conversation metadata, participants and provenance appear here."}
              </p>
            </div>
            <div className="flex items-center gap-1.5">
              {highlight ? <Badge tone="amber">filter: {highlight}</Badge> : null}
              <Badge>{num(visible.length)} shown</Badge>
            </div>
          </header>

          <div className="min-h-0 flex-1 overflow-y-auto px-4 py-3 scroll-thin">
            {conversationApi.loading ? <Spinner label="Loading messages…" /> : null}
            {conversationApi.error ? <ErrorState error={conversationApi.error} onRetry={conversationApi.reload} /> : null}
            {!conversationApi.loading && visible.length === 0 ? (
              <EmptyState icon={<MessageSquare className="h-7 w-7" />} title="No messages to show" description="Load older messages or clear the media filter." />
            ) : null}
            <div className="mx-auto max-w-3xl space-y-1.5">
              {visible.map((message, index) => {
                const previous = visible[index - 1];
                const newDay = !previous || dateOnly(previous.sent_at_utc) !== dateOnly(message.sent_at_utc);
                const isOwner = message.sender_raw.toLowerCase() === "you";
                const matches =
                  highlight.trim().length > 1 &&
                  message.body.toLowerCase().includes(highlight.trim().toLowerCase());
                return (
                  <React.Fragment key={message.id}>
                    {newDay ? (
                      <div className="flex items-center gap-2 py-2">
                        <span className="h-px flex-1 bg-line/70" />
                        <span className="rounded-full border border-line bg-panel px-2 py-0.5 text-[10px] text-muted">
                          {dateOnly(message.sent_at_utc)}
                        </span>
                        <span className="h-px flex-1 bg-line/70" />
                      </div>
                    ) : null}
                    {message.is_system ? (
                      <div className="bubble-system">
                        <ShieldQuestion className="mr-1 inline h-3 w-3" />
                        {message.body || "(system notice)"}
                      </div>
                    ) : (
                      <div className={`group flex ${isOwner ? "justify-end" : "justify-start"}`}>
                        <div className={`max-w-[78%] ${matches ? "ring-1 ring-amber/60" : ""}`}>
                          <div className="mb-0.5 flex items-center gap-1.5 px-1 text-[10px] text-muted">
                            <span className="font-medium text-ink/80">{message.sender_raw || "unknown"}</span>
                            <span>{timeOnly(message.sent_at_utc)}</span>
                            {message.is_edited ? <Badge tone="amber">edited</Badge> : null}
                            {message.is_deleted ? <Badge tone="danger">deleted</Badge> : null}
                            {message.has_media ? <Badge tone="teal">{message.media_ref ?? "media"}</Badge> : null}
                          </div>
                          <div className={isOwner ? "bubble-out" : "bubble-in"}>
                            <p className={`whitespace-pre-wrap break-words text-[12.5px] leading-relaxed ${message.is_deleted ? "italic text-muted" : "text-ink"}`}>
                              {message.body || <span className="text-muted">(no text)</span>}
                            </p>
                          </div>
                          <div className="mt-0.5 flex items-center gap-1.5 px-1 opacity-0 transition group-hover:opacity-100">
                            <button className="text-[10px] text-muted hover:text-accent" onClick={() => setInspect(message.id)}>
                              inspect evidence
                            </button>
                            <button
                              className={`text-[10px] ${message.bookmarked ? "text-amber" : "text-muted hover:text-amber"}`}
                              onClick={() => void toggleBookmark(message)}
                            >
                              <Bookmark className="mr-0.5 inline h-2.5 w-2.5" />
                              {message.bookmarked ? "bookmarked" : "bookmark"}
                            </button>
                            {message.parse_confidence < 0.8 ? (
                              <span className="text-[10px] text-amber">low confidence parse</span>
                            ) : null}
                          </div>
                        </div>
                      </div>
                    )}
                  </React.Fragment>
                );
              })}
            </div>
          </div>

          <footer className="flex items-center justify-between border-t border-line px-4 py-1.5 text-[10.5px] text-muted">
            <span>
              {conversationApi.data ? `${num(messages.length)} of ${num(conversationApi.data.total)} messages loaded` : ""}
            </span>
            <span>Timestamps shown in your local time · source data stored in UTC</span>
          </footer>
        </section>
      </div>

      <MessageInspector
        caseId={caseId}
        messageId={inspect}
        open={Boolean(inspect)}
        onClose={() => {
          setInspect(null);
          const next = new URLSearchParams(params);
          next.delete("m");
          setParams(next, { replace: true });
        }}
        onChanged={() => conversationApi.reload()}
      />
    </div>
  );
}
