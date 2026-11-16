import { Bookmark, Copy, FileWarning, Hash, Paperclip, Tag, Trash2 } from "lucide-react";
import * as React from "react";
import { Drawer } from "@/components/ui/dialog";
import { Badge, Button, EmptyState, ErrorState, Field, Input, Spinner, Textarea } from "@/components/ui/primitives";
import { useApi } from "@/hooks/useApi";
import { apiUrl, del, post, withToken } from "@/lib/api";
import { bytes, dateTime, num } from "@/lib/format";
import { useApp } from "@/stores/app";
import type { MessageDetail } from "@/types";

/**
 * Evidence-anchored message view: raw record, provenance, attachments,
 * annotations. Used by the explorer, search results and AI citations.
 */
export function MessageInspector({
  caseId,
  messageId,
  open,
  onClose,
  onChanged,
}: {
  caseId: string;
  messageId: string | null;
  open: boolean;
  onClose: () => void;
  onChanged?: () => void;
}) {
  const { data, error, loading, reload } = useApi<MessageDetail>(
    messageId ? `/api/cases/${caseId}/messages/${messageId}` : null,
    [messageId],
  );
  const toast = useApp((state) => state.toast);
  const [tag, setTag] = React.useState("");
  const [note, setNote] = React.useState("");
  const [busy, setBusy] = React.useState(false);

  const run = async (action: () => Promise<unknown>, message: string) => {
    setBusy(true);
    try {
      await action();
      toast({ title: message, tone: "success" });
      reload();
      onChanged?.();
    } catch (err) {
      toast({ title: "Action failed", description: (err as Error).message, tone: "error" });
    } finally {
      setBusy(false);
    }
  };

  return (
    <Drawer open={open} onClose={onClose} title="Message evidence" width="lg">
      {loading ? <Spinner /> : null}
      {error ? <ErrorState error={error} onRetry={reload} /> : null}
      {data ? (
        <div className="space-y-4">
          <div className="surface-muted p-3">
            <div className="mb-1.5 flex flex-wrap items-center gap-1.5">
              <Badge tone="accent">{data.sender_raw || "system"}</Badge>
              <Badge>{data.message_type}</Badge>
              {data.is_deleted ? <Badge tone="danger">deleted marker</Badge> : null}
              {data.is_edited ? <Badge tone="amber">edited marker</Badge> : null}
              {data.is_forwarded ? <Badge>forwarded</Badge> : null}
              {data.has_media ? <Badge tone="teal">media</Badge> : null}
              {data.bookmark ? <Badge tone="amber">bookmarked</Badge> : null}
            </div>
            <p className="whitespace-pre-wrap break-words text-[13px] leading-relaxed text-ink">
              {data.body || <span className="text-muted">(no text content)</span>}
            </p>
            <p className="mt-2 text-[11px] text-muted">
              {dateTime(data.sent_at_utc)} UTC · local {data.sent_at_local} (offset{" "}
              {data.tz_offset_min >= 0 ? "+" : ""}
              {data.tz_offset_min} min)
            </p>
          </div>

          <div className="grid grid-cols-2 gap-2 text-[11.5px]">
            <Info label="Conversation" value={data.conversation_title} />
            <Info label="Original timestamp" value={data.original_timestamp} />
            <Info label="Source reference" value={data.source_ref} mono />
            <Info label="Parse confidence" value={`${(data.parse_confidence * 100).toFixed(0)}%`} />
            <Info label="Characters / words" value={`${num(data.char_count)} / ${num(data.word_count)}`} />
            <Info label="Session" value={data.session_id ?? "—"} mono />
          </div>

          <section>
            <h3 className="section-title mb-1.5">Provenance</h3>
            <div className="space-y-1.5">
              {data.observations.map((observation) => (
                <div key={`${observation.evidence_id}-${observation.source_ref}`} className="surface-muted px-2.5 py-2">
                  <p className="text-[12px] text-ink">{observation.original_name}</p>
                  <p className="mono mt-0.5 truncate text-muted" title={observation.sha256}>
                    sha256 {observation.sha256}
                  </p>
                  <p className="text-[11px] text-muted">observed at {observation.source_ref}</p>
                </div>
              ))}
            </div>
          </section>

          {data.versions.length > 0 ? (
            <section>
              <h3 className="section-title mb-1.5">Conflicting versions in other snapshots</h3>
              {data.versions.map((version) => (
                <div key={version.version} className="surface-muted mb-1.5 p-2.5">
                  <p className="text-[11px] text-amber">
                    version {version.version} · observed {dateTime(version.observed_at)}
                  </p>
                  <p className="mt-1 whitespace-pre-wrap text-[12.5px] text-ink">{version.body}</p>
                </div>
              ))}
            </section>
          ) : null}

          {data.attachments.length > 0 ? (
            <section>
              <h3 className="section-title mb-1.5">Attachments</h3>
              <div className="space-y-1.5">
                {data.attachments.map((attachment) => (
                  <div key={attachment.id} className="surface-muted flex items-center gap-2 p-2">
                    {attachment.media_type === "image" ? (
                      <img
                        src={withToken(`/api/cases/${caseId}/media/${attachment.id}/thumb`)}
                        alt=""
                        className="h-12 w-12 rounded border border-line object-cover"
                      />
                    ) : (
                      <Paperclip className="h-4 w-4 text-muted" />
                    )}
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-[12px] text-ink">{attachment.file_name}</p>
                      <p className="text-[10.5px] text-muted">
                        {attachment.media_type} · {bytes(attachment.size_bytes)}
                        {attachment.duration_ms ? ` · ${(attachment.duration_ms / 1000).toFixed(1)}s` : ""}
                      </p>
                    </div>
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={() => window.open(apiUrl(`/api/cases/${caseId}/media/${attachment.id}/file`), "_blank")}
                    >
                      Open
                    </Button>
                  </div>
                ))}
              </div>
            </section>
          ) : null}

          {data.references.length > 0 ? (
            <section>
              <h3 className="section-title mb-1.5">Extracted references</h3>
              <div className="flex flex-wrap gap-1.5">
                {data.references.map((reference, index) => (
                  <span key={index} className="chip">
                    <Hash className="h-3 w-3" />
                    {reference.ref_type}: {reference.ref_value}
                  </span>
                ))}
              </div>
            </section>
          ) : null}

          <section className="grid gap-3 sm:grid-cols-2">
            <div>
              <h3 className="section-title mb-1.5">Tags</h3>
              <div className="mb-1.5 flex flex-wrap gap-1">
                {data.tags.length === 0 ? <span className="text-[11px] text-muted">No tags</span> : null}
                {data.tags.map((item) => (
                  <span key={item} className="chip">
                    <Tag className="h-3 w-3" /> {item}
                    <button
                      className="ml-1 text-muted hover:text-danger"
                      onClick={() => void run(() => del(`/api/cases/${caseId}/tags/${data.id}?tag=${encodeURIComponent(item)}`), "Tag removed")}
                    >
                      <Trash2 className="h-3 w-3" />
                    </button>
                  </span>
                ))}
              </div>
              <div className="flex gap-1.5">
                <Input value={tag} onChange={(event) => setTag(event.target.value)} placeholder="add tag" className="h-8 text-[12px]" />
                <Button
                  size="sm"
                  loading={busy}
                  onClick={() =>
                    void run(async () => {
                      await post(`/api/cases/${caseId}/tags`, { message_id: data.id, tag });
                      setTag("");
                    }, "Tag added")
                  }
                >
                  Add
                </Button>
              </div>
            </div>
            <div>
              <h3 className="section-title mb-1.5">Bookmark</h3>
              <Button
                variant={data.bookmark ? "danger" : "default"}
                size="sm"
                className="w-full"
                loading={busy}
                onClick={() =>
                  void run(
                    () =>
                      data.bookmark
                        ? del(`/api/cases/${caseId}/bookmarks/${data.id}`)
                        : post(`/api/cases/${caseId}/bookmarks`, { message_id: data.id, label: "key evidence" }),
                    data.bookmark ? "Bookmark removed" : "Message bookmarked",
                  )
                }
              >
                <Bookmark className="h-3.5 w-3.5" />
                {data.bookmark ? "Remove bookmark" : "Bookmark this message"}
              </Button>
            </div>
          </section>

          <section>
            <h3 className="section-title mb-1.5">Investigation notes</h3>
            <div className="mb-2 space-y-1.5">
              {data.notes.length === 0 ? <p className="text-[11px] text-muted">No notes on this message.</p> : null}
              {data.notes.map((item) => (
                <div key={item.id} className="surface-muted p-2.5">
                  <p className="whitespace-pre-wrap text-[12px] text-ink">{item.body}</p>
                  <p className="mt-1 text-[10.5px] text-muted">
                    {item.author} · {dateTime(item.created_at)}
                  </p>
                </div>
              ))}
            </div>
            <Field label="Add a note">
              <Textarea
                value={note}
                onChange={(event) => setNote(event.target.value)}
                placeholder="Analyst observation linked to this message…"
              />
            </Field>
            <div className="mt-2 flex justify-end">
              <Button
                size="sm"
                variant="primary"
                loading={busy}
                disabled={!note.trim()}
                onClick={() =>
                  void run(async () => {
                    await post(`/api/cases/${caseId}/notes`, { body: note, message_id: data.id });
                    setNote("");
                  }, "Note saved")
                }
              >
                Save note
              </Button>
            </div>
          </section>

          <div className="flex items-center justify-between border-t border-line pt-3">
            <span className="flex items-center gap-1 text-[10.5px] text-muted">
              <FileWarning className="h-3 w-3" /> Evidence is read-only; annotations are separate records.
            </span>
            <Button
              size="sm"
              variant="ghost"
              onClick={() => {
                void navigator.clipboard?.writeText(JSON.stringify(data, null, 2));
                toast({ title: "Message record copied", tone: "info" });
              }}
            >
              <Copy className="h-3.5 w-3.5" /> Copy JSON
            </Button>
          </div>
        </div>
      ) : null}
      {!loading && !error && !data ? <EmptyState title="Select a message" /> : null}
    </Drawer>
  );
}

function Info({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="surface-muted px-2.5 py-1.5">
      <p className="text-[9.5px] uppercase tracking-[0.08em] text-muted">{label}</p>
      <p className={`truncate text-[12px] text-ink ${mono ? "mono" : ""}`} title={value}>
        {value}
      </p>
    </div>
  );
}
