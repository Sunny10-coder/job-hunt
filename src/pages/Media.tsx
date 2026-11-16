import { FileText, Image as ImageIcon, Music, PlayCircle } from "lucide-react";
import * as React from "react";
import { PageHeader } from "@/components/layout/PageHeader";
import { Dialog } from "@/components/ui/dialog";
import { Badge, Button, EmptyState, ErrorState, Input, Panel, Spinner, Tabs } from "@/components/ui/primitives";
import { post, withToken } from "@/lib/api";
import { bytes, dateTime, num } from "@/lib/format";
import { useApi } from "@/hooks/useApi";
import { useCase } from "@/hooks/useCaseContext";
import { useApp } from "@/stores/app";
import type { Attachment } from "@/types";

type MediaTab = "all" | "image" | "video" | "audio" | "document";

export function MediaPage() {
  const { caseId } = useCase();
  const toast = useApp((state) => state.toast);
  const [tab, setTab] = React.useState<MediaTab>("all");
  const [search, setSearch] = React.useState("");
  const [selected, setSelected] = React.useState<Attachment | null>(null);
  const [view, setView] = React.useState<"gallery" | "duplicates" | "missing">("gallery");

  const mediaApi = useApi<{ total: number; items: Attachment[] }>(
    caseId ? `/api/cases/${caseId}/media?type=${tab}&q=${encodeURIComponent(search)}&limit=120` : null,
    [caseId, tab, search],
  );
  const duplicatesApi = useApi<{ exact_duplicates: { sha256: string; count: number; names: string }[]; perceptual_duplicates: { phash: string; count: number; names: string }[]; method: string }>(
    caseId && view === "duplicates" ? `/api/cases/${caseId}/media/duplicates` : null,
    [caseId, view],
  );
  const missingApi = useApi<{ placeholders: { id: string; sent_at_utc: string; sender_raw: string; message_type: string; media_ref: string | null; conversation: string }[]; unlinked_files: { id: string; file_name: string; media_type: string; size_bytes: number }[]; note: string }>(
    caseId && view === "missing" ? `/api/cases/${caseId}/media/missing` : null,
    [caseId, view],
  );

  const inspect = async (attachment: Attachment) => {
    setSelected(attachment);
    if (!attachment.meta || Object.keys(attachment.meta).length === 0) {
      try {
        const detailed = await post<Attachment & { meta: Record<string, unknown> }>(`/api/cases/${caseId}/media/${attachment.id}/inspect`);
        setSelected(detailed);
      } catch (err) {
        toast({ title: "Inspection failed", description: (err as Error).message, tone: "error" });
      }
    }
  };

  return (
    <div className="flex h-full min-h-0 flex-col">
      <PageHeader
        title="Media forensics"
        description="Attachments extracted from evidence. Metadata is reported as found — consistent EXIF never proves an image is authentic or unmodified."
        badges={<Badge tone="teal">{num(mediaApi.data?.total ?? 0)} artifacts</Badge>}
        actions={
          <Tabs
            value={view}
            onChange={setView}
            tabs={[
              { value: "gallery", label: "Library" },
              { value: "duplicates", label: "Duplicates" },
              { value: "missing", label: "Missing media" },
            ]}
          />
        }
      />

      {view === "gallery" ? (
        <>
          <div className="flex flex-wrap items-center gap-2 border-b border-line bg-panel/50 px-4 py-2">
            <Tabs
              value={tab}
              onChange={setTab}
              tabs={[
                { value: "all", label: "All" },
                { value: "image", label: "Images" },
                { value: "video", label: "Video" },
                { value: "audio", label: "Audio" },
                { value: "document", label: "Documents" },
              ]}
            />
            <Input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search file names" className="ml-auto h-8 w-56 text-[12px]" />
          </div>
          <div className="min-h-0 flex-1 overflow-y-auto p-4 scroll-thin">
            {mediaApi.loading && !mediaApi.data ? <Spinner /> : null}
            {mediaApi.error ? <ErrorState error={mediaApi.error} onRetry={mediaApi.reload} /> : null}
            {mediaApi.data && mediaApi.data.items.length === 0 ? (
              <EmptyState
                icon={<ImageIcon className="h-7 w-7" />}
                title="No media artifacts"
                description="Media is registered when a ZIP export contains files or when standalone media is imported. WhatsApp text exports often say '<Media omitted>' without including the file."
              />
            ) : null}
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-6">
              {(mediaApi.data?.items ?? []).map((item) => (
                <button
                  key={item.id}
                  onClick={() => void inspect(item)}
                  className="surface group overflow-hidden text-left transition hover:border-accent/40"
                >
                  <div className="flex h-28 items-center justify-center border-b border-line bg-elevated/60">
                    {item.media_type === "image" ? (
                      <img
                        src={withToken(`/api/cases/${caseId}/media/${item.id}/thumb`)}
                        alt={item.file_name}
                        className="h-full w-full object-cover"
                        onError={(event) => {
                          (event.currentTarget as HTMLImageElement).style.display = "none";
                        }}
                      />
                    ) : item.media_type === "video" ? (
                      <PlayCircle className="h-7 w-7 text-muted" />
                    ) : item.media_type === "audio" ? (
                      <Music className="h-7 w-7 text-muted" />
                    ) : (
                      <FileText className="h-7 w-7 text-muted" />
                    )}
                  </div>
                  <div className="p-2">
                    <p className="truncate text-[11.5px] text-ink" title={item.file_name}>
                      {item.file_name}
                    </p>
                    <p className="text-[10px] text-muted">
                      {bytes(item.size_bytes)} · {item.missing ? "missing" : item.linked ? "linked" : "unlinked"}
                    </p>
                  </div>
                </button>
              ))}
            </div>
          </div>
        </>
      ) : view === "duplicates" ? (
        <div className="min-h-0 flex-1 overflow-y-auto p-4 scroll-thin">
          {duplicatesApi.loading ? <Spinner /> : null}
          {duplicatesApi.error ? <ErrorState error={duplicatesApi.error} onRetry={duplicatesApi.reload} /> : null}
          {duplicatesApi.data ? (
            <div className="grid gap-3 lg:grid-cols-2">
              <Panel title="Identical files (SHA-256)" dense>
                <div className="divide-y divide-line/60">
                  {duplicatesApi.data.exact_duplicates.map((group) => (
                    <div key={group.sha256} className="px-3 py-2">
                      <p className="mono truncate text-[10.5px] text-accent">{group.sha256}</p>
                      <p className="text-[11.5px] text-ink">{group.count} copies</p>
                      <p className="text-[10.5px] text-muted">{group.names}</p>
                    </div>
                  ))}
                  {duplicatesApi.data.exact_duplicates.length === 0 ? <EmptyState title="No exact duplicates" /> : null}
                </div>
              </Panel>
              <Panel title="Visually similar (perceptual hash)" dense>
                <div className="divide-y divide-line/60">
                  {duplicatesApi.data.perceptual_duplicates.map((group) => (
                    <div key={group.phash} className="px-3 py-2">
                      <p className="mono text-[10.5px] text-teal">{group.phash}</p>
                      <p className="text-[11.5px] text-ink">{group.count} similar images</p>
                      <p className="text-[10.5px] text-muted">{group.names}</p>
                    </div>
                  ))}
                  {duplicatesApi.data.perceptual_duplicates.length === 0 ? <EmptyState title="No perceptual duplicates" /> : null}
                </div>
                <p className="p-3 text-[10.5px] leading-relaxed text-muted">{duplicatesApi.data.method}</p>
              </Panel>
            </div>
          ) : null}
        </div>
      ) : (
        <div className="min-h-0 flex-1 overflow-y-auto p-4 scroll-thin">
          {missingApi.loading ? <Spinner /> : null}
          {missingApi.error ? <ErrorState error={missingApi.error} onRetry={missingApi.reload} /> : null}
          {missingApi.data ? (
            <div className="grid gap-3 lg:grid-cols-2">
              <Panel title="Media placeholders without files" dense>
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>When</th>
                      <th>Sender</th>
                      <th>Type</th>
                      <th>Conversation</th>
                    </tr>
                  </thead>
                  <tbody>
                    {missingApi.data.placeholders.map((row) => (
                      <tr key={row.id}>
                        <td className="text-[10.5px] text-muted">{dateTime(row.sent_at_utc)}</td>
                        <td>{row.sender_raw}</td>
                        <td>{row.message_type}</td>
                        <td className="text-[11px]">{row.conversation}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                <p className="p-2 text-[10.5px] text-muted">{missingApi.data.note}</p>
              </Panel>
              <Panel title="Files not referenced by any message" dense>
                <div className="divide-y divide-line/60">
                  {missingApi.data.unlinked_files.map((file) => (
                    <div key={file.id} className="px-3 py-2">
                      <p className="truncate text-[11.5px] text-ink">{file.file_name}</p>
                      <p className="text-[10.5px] text-muted">
                        {file.media_type} · {bytes(file.size_bytes)} — association would be a guess, so none is recorded.
                      </p>
                    </div>
                  ))}
                  {missingApi.data.unlinked_files.length === 0 ? <EmptyState title="Every file is referenced" /> : null}
                </div>
              </Panel>
            </div>
          ) : null}
        </div>
      )}

      <Dialog open={Boolean(selected)} onClose={() => setSelected(null)} title={selected?.file_name} description={selected ? `${selected.media_type} · ${bytes(selected.size_bytes)}` : undefined} width="lg"
        footer={
          selected ? (
            <>
              <Button variant="ghost" onClick={() => setSelected(null)}>Close</Button>
              <Button variant="primary" onClick={() => window.open(withToken(`/api/cases/${caseId}/media/${selected.id}/file`), "_blank")}>
                Open original
              </Button>
            </>
          ) : null
        }
      >
        {selected ? (
          <div className="space-y-3">
            {selected.media_type === "image" ? (
              <img src={withToken(`/api/cases/${caseId}/media/${selected.id}/file`)} alt={selected.file_name} className="max-h-72 w-full rounded-lg border border-line object-contain" />
            ) : null}
            {selected.media_type === "audio" ? (
              <audio controls className="w-full" src={withToken(`/api/cases/${caseId}/media/${selected.id}/file`)} />
            ) : null}
            {selected.media_type === "video" ? (
              <video controls className="max-h-72 w-full rounded-lg border border-line" src={withToken(`/api/cases/${caseId}/media/${selected.id}/file`)} />
            ) : null}
            <div className="grid grid-cols-2 gap-2 text-[11.5px]">
              <Detail label="SHA-256" value={selected.sha256 ?? "not computed"} mono />
              <Detail label="Dimensions" value={selected.width && selected.height ? `${selected.width} × ${selected.height}` : "—"} />
              <Detail label="Duration" value={selected.duration_ms ? `${(selected.duration_ms / 1000).toFixed(2)} s` : "—"} />
              <Detail label="Linked to message" value={selected.linked ? "yes" : "no (not referenced)"} />
            </div>
            {selected.meta && Object.keys(selected.meta).length > 0 ? (
              <div>
                <p className="section-title mb-1">Metadata</p>
                <pre className="mono max-h-64 overflow-auto rounded-lg border border-line bg-elevated/60 p-2 text-[10.5px] scroll-thin">
                  {JSON.stringify(selected.meta, null, 2)}
                </pre>
                <p className="mt-1 text-[10.5px] text-muted">
                  Embedded metadata can be absent, stripped or manipulated; it is reported, not trusted.
                </p>
              </div>
            ) : null}
          </div>
        ) : null}
      </Dialog>
    </div>
  );
}

function Detail({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="surface-muted px-2.5 py-1.5">
      <p className="text-[9.5px] uppercase tracking-[0.08em] text-muted">{label}</p>
      <p className={`break-all text-[11.5px] text-ink ${mono ? "mono" : ""}`}>{value}</p>
    </div>
  );
}
