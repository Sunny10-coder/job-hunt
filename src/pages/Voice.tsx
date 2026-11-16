import { AudioLines, Mic, Search, Wand2 } from "lucide-react";
import * as React from "react";
import { PageHeader } from "@/components/layout/PageHeader";
import { Badge, Button, EmptyState, ErrorState, Field, Input, Panel, Spinner, Textarea } from "@/components/ui/primitives";
import { patch, post, withToken } from "@/lib/api";
import { dateTime } from "@/lib/format";
import { useApi } from "@/hooks/useApi";
import { useCase } from "@/hooks/useCaseContext";
import { useApp } from "@/stores/app";
import type { Attachment } from "@/types";

interface Transcript {
  id: string;
  attachment_id: string;
  file_name: string;
  text: string;
  language: string | null;
  model: string;
  confidence: number | null;
  duration_ms: number | null;
  created_at: string;
  edited: number;
  sent_at_utc: string | null;
  sender_raw: string | null;
  conversation: string | null;
}

export function VoicePage() {
  const { caseId } = useCase();
  const toast = useApp((state) => state.toast);
  const [query, setQuery] = React.useState("");
  const [busy, setBusy] = React.useState<string | null>(null);
  const [editing, setEditing] = React.useState<Transcript | null>(null);
  const [draft, setDraft] = React.useState("");

  const audioApi = useApi<{ total: number; items: Attachment[] }>(caseId ? `/api/cases/${caseId}/media?type=audio&limit=200` : null, [caseId]);
  const transcriptsApi = useApi<{ transcripts: Transcript[]; engine: { available: boolean; whisper_cpp: string | null; faster_whisper: boolean; hint: string } }>(
    caseId ? `/api/cases/${caseId}/transcripts` : null,
    [caseId],
  );

  const transcribe = async (attachmentId: string) => {
    setBusy(attachmentId);
    try {
      await post(`/api/cases/${caseId}/audio/${attachmentId}/transcribe`, {});
      transcriptsApi.reload();
      toast({ title: "Transcription stored", tone: "success" });
    } catch (err) {
      toast({
        title: "Transcription unavailable",
        description: (err as Error).message,
        tone: "error",
      });
    } finally {
      setBusy(null);
    }
  };

  const filtered = (transcriptsApi.data?.transcripts ?? []).filter((transcript) =>
    !query.trim() || transcript.text?.toLowerCase().includes(query.toLowerCase()),
  );

  return (
    <div className="flex h-full min-h-0 flex-col">
      <PageHeader
        title="Voice & audio intelligence"
        description="Local playback, waveform and offline transcription for voice notes. No audio is uploaded to a service; engine coverage depends on the installed local model."
        badges={
          transcriptsApi.data ? (
            <Badge tone={transcriptsApi.data.engine.available ? "teal" : "amber"}>
              {transcriptsApi.data.engine.available ? "local STT ready" : "no local STT model"}
            </Badge>
          ) : null
        }
      />
      <div className="grid min-h-0 flex-1 grid-cols-[320px_minmax(0,1fr)]">
        <aside className="min-h-0 overflow-y-auto border-r border-line bg-panel/40 scroll-thin">
          <div className="border-b border-line p-2">
            <div className="relative">
              <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted" />
              <Input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search transcripts" className="h-8 pl-8 text-[12px]" />
            </div>
          </div>
          {audioApi.loading ? <Spinner /> : null}
          {audioApi.error ? <ErrorState error={audioApi.error} onRetry={audioApi.reload} /> : null}
          {(audioApi.data?.items ?? []).map((item) => (
            <div key={item.id} className="border-b border-line/50 px-3 py-2">
              <div className="flex items-center justify-between gap-2">
                <span className="truncate text-[12px] text-ink">{item.file_name}</span>
                {item.duration_ms ? <Badge>{(item.duration_ms / 1000).toFixed(1)}s</Badge> : null}
              </div>
              <audio controls preload="none" className="mt-1 h-8 w-full" src={withToken(`/api/cases/${caseId}/media/${item.id}/file`)} />
              <div className="mt-1 flex items-center justify-between">
                <span className="text-[10px] text-muted">{item.sent_at_utc ? dateTime(item.sent_at_utc) : "unlinked audio"}</span>
                <Button size="sm" variant="ghost" loading={busy === item.id} onClick={() => void transcribe(item.id)}>
                  <Wand2 className="h-3 w-3" /> Transcribe
                </Button>
              </div>
              {Array.isArray((item.meta as { waveform?: number[] })?.waveform) ? (
                <div className="mt-1 flex h-6 items-end gap-[1px]">
                  {((item.meta as { waveform: number[] }).waveform ?? []).map((peak, index) => (
                    <span key={index} className="w-[2px] rounded-sm bg-teal/70" style={{ height: `${Math.max(8, peak * 100)}%` }} />
                  ))}
                </div>
              ) : null}
            </div>
          ))}
          {(audioApi.data?.items ?? []).length === 0 && !audioApi.loading ? (
            <EmptyState icon={<AudioLines className="h-7 w-7" />} title="No audio artifacts" description="Import a media-inclusive ZIP export or standalone voice notes." />
          ) : null}
        </aside>

        <div className="min-h-0 overflow-y-auto p-4 scroll-thin">
          {transcriptsApi.data && !transcriptsApi.data.engine.available ? (
            <Panel title="Local transcription engine not installed">
              <p className="text-[11.5px] leading-relaxed text-muted">{transcriptsApi.data.engine.hint}</p>
              <p className="mt-2 text-[11px] text-muted">
                Transcripts remain optional: playback, waveform, duration and metadata all work without an
                engine. When a model is installed, transcription runs entirely on this machine.
              </p>
            </Panel>
          ) : null}

          <div className="mt-3 space-y-3">
            {transcriptsApi.loading ? <Spinner /> : null}
            {transcriptsApi.error ? <ErrorState error={transcriptsApi.error} onRetry={transcriptsApi.reload} /> : null}
            {filtered.map((transcript) => (
              <Panel
                key={transcript.id}
                title={transcript.file_name}
                subtitle={`${transcript.model} · ${transcript.language ?? "unknown"} · ${transcript.confidence !== null ? `confidence ${transcript.confidence}` : "confidence not reported"}${transcript.edited ? " · edited by analyst" : ""}`}
                actions={
                  <Button size="sm" variant="ghost" onClick={() => { setEditing(transcript); setDraft(transcript.text); }}>
                    Edit
                  </Button>
                }
              >
                <p className="whitespace-pre-wrap text-[12.5px] leading-relaxed text-ink">{transcript.text || "(empty transcript)"}</p>
                <p className="mt-2 text-[10.5px] text-muted">
                  {transcript.sent_at_utc ? `${transcript.sender_raw} · ${dateTime(transcript.sent_at_utc)}` : "not linked to a message"}
                  {transcript.conversation ? ` · ${transcript.conversation}` : ""}
                </p>
              </Panel>
            ))}
            {filtered.length === 0 && !transcriptsApi.loading ? (
              <Panel>
                <EmptyState
                  icon={<Mic className="h-7 w-7" />}
                  title="No transcripts yet"
                  description="Transcribe an audio file from the list. Speaker identity is never asserted from voice characteristics alone."
                />
              </Panel>
            ) : null}
          </div>
        </div>
      </div>

      {editing ? (
        <div className="fixed inset-0 z-40 flex items-center justify-center bg-black/50 p-6">
          <div className="surface w-full max-w-2xl p-4">
            <Field label={`Correct transcript — ${editing.file_name}`} hint="edits are recorded as analyst changes">
              <Textarea value={draft} onChange={(event) => setDraft(event.target.value)} className="min-h-[180px]" />
            </Field>
            <div className="mt-3 flex justify-end gap-2">
              <Button variant="ghost" onClick={() => setEditing(null)}>Cancel</Button>
              <Button
                variant="primary"
                onClick={async () => {
                  await patch(`/api/transcripts/${editing.id}`, { text: draft });
                  setEditing(null);
                  transcriptsApi.reload();
                  toast({ title: "Transcript updated", tone: "success" });
                }}
              >
                Save correction
              </Button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
