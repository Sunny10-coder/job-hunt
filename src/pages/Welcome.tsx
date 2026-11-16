import {
  ArchiveRestore,
  ArrowRight,
  Database,
  FolderLock,
  HardDrive,
  Plus,
  ShieldCheck,
  Trash2,
  WifiOff,
} from "lucide-react";
import * as React from "react";
import { useNavigate } from "react-router-dom";
import { PageBody, PageHeader } from "@/components/layout/PageHeader";
import { Dialog } from "@/components/ui/dialog";
import {
  Badge,
  Button,
  Checkbox,
  EmptyState,
  ErrorState,
  Field,
  Input,
  Panel,
  Spinner,
  Textarea,
} from "@/components/ui/primitives";
import { del, get, patch, post } from "@/lib/api";
import { bytes, num, relative } from "@/lib/format";
import { useApi } from "@/hooks/useApi";
import { useApp } from "@/stores/app";
import type { CaseSummary } from "@/types";

interface Diagnostics {
  engine_version: string;
  python: string;
  platform: string;
  sqlite: string;
  fts5: boolean;
  data_dir: string;
  db_bytes: number;
  disk_free_bytes: number;
  cases: number;
  messages: number;
  ai: { ok: boolean; provider: string | null; models: string[]; error?: string; external?: boolean };
  transcription: { available: boolean; whisper_cpp: string | null; faster_whisper: boolean };
  media_tools: { exiftool: string | null; ffprobe: string | null; ffmpeg: string | null; pillow: boolean };
  offline_capable: boolean;
}

export function Welcome() {
  const navigate = useNavigate();
  const { cases, setCases, recentCaseIds, toast } = useApp();
  const { data: diagnostics } = useApi<Diagnostics>("/api/diagnostics");
  const [createOpen, setCreateOpen] = React.useState(false);
  const [restoreOpen, setRestoreOpen] = React.useState(false);
  const [form, setForm] = React.useState({ name: "", description: "", examiner: "" });
  const [ack, setAck] = React.useState(false);
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [restore, setRestore] = React.useState({ path: "", password: "", name: "" });

  const reload = React.useCallback(async () => {
    try {
      setCases(await get<CaseSummary[]>("/api/cases"));
    } catch (err) {
      toast({ title: "Could not load cases", description: (err as Error).message, tone: "error" });
    }
  }, [setCases, toast]);

  React.useEffect(() => {
    void reload();
  }, [reload]);

  const createCase = async () => {
    setBusy(true);
    setError(null);
    try {
      const created = await post<CaseSummary>("/api/cases", {
        ...form,
        authorization_acknowledged: ack,
      });
      await reload();
      setCreateOpen(false);
      setForm({ name: "", description: "", examiner: "" });
      setAck(false);
      toast({ title: `Case CASE-${String(created.case_number).padStart(4, "0")} created`, tone: "success" });
      navigate(`/cases/${created.id}`);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const restoreCase = async () => {
    setBusy(true);
    setError(null);
    try {
      const result = await post<{ case: CaseSummary }>("/api/cases/restore", {
        path: restore.path,
        password: restore.password,
        name: restore.name || undefined,
      });
      await reload();
      setRestoreOpen(false);
      toast({ title: "Case restored from encrypted backup", tone: "success" });
      navigate(`/cases/${result.case.id}`);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const recent = React.useMemo(
    () =>
      [...cases].sort(
        (a, b) => (recentCaseIds.indexOf(b.id) === -1 ? 1 : 0) - (recentCaseIds.indexOf(a.id) === -1 ? 1 : 0),
      ),
    [cases, recentCaseIds],
  );

  return (
    <div className="flex h-full min-h-0 flex-col">
      <PageHeader
        title="Investigation workspace"
        description="Local-first forensic analysis of WhatsApp evidence you own or are authorised to examine. Nothing leaves this computer unless you explicitly enable an external AI provider."
        actions={
          <>
            <Button variant="ghost" onClick={() => setRestoreOpen(true)}>
              <ArchiveRestore className="h-3.5 w-3.5" /> Restore backup
            </Button>
            <Button variant="primary" onClick={() => setCreateOpen(true)}>
              <Plus className="h-3.5 w-3.5" /> New case
            </Button>
          </>
        }
        badges={
          <>
            <Badge tone="teal">
              <WifiOff className="h-3 w-3" /> offline capable
            </Badge>
            {diagnostics?.fts5 ? <Badge tone="accent">FTS5 indexed</Badge> : null}
          </>
        }
      />
      <PageBody className="p-4">
        <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_340px]">
          <div className="space-y-3">
            {recent.length === 0 ? (
              <Panel>
                <EmptyState
                  icon={<FolderLock className="h-8 w-8" />}
                  title="No cases yet"
                  description="Create an investigation case, then import a WhatsApp export (TXT or ZIP). Originals are hashed with SHA-256 at ingestion and never modified."
                  action={
                    <Button variant="primary" onClick={() => setCreateOpen(true)}>
                      <Plus className="h-3.5 w-3.5" /> Create the first case
                    </Button>
                  }
                />
              </Panel>
            ) : (
              recent.map((item) => (
                <article key={item.id} className="surface group flex items-center gap-3 px-4 py-3 transition hover:border-accent/35">
                  <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl border border-line bg-elevated">
                    <Database className="h-4 w-4 text-accent" />
                  </div>
                  <button className="min-w-0 flex-1 text-left" onClick={() => navigate(`/cases/${item.id}`)}>
                    <div className="flex flex-wrap items-center gap-1.5">
                      <span className="mono text-[11px] text-muted">CASE-{String(item.case_number).padStart(4, "0")}</span>
                      <h2 className="truncate text-[13.5px] font-semibold text-ink">{item.name}</h2>
                      {item.status === "archived" ? <Badge tone="amber">archived</Badge> : null}
                    </div>
                    <p className="mt-0.5 line-clamp-1 text-[11.5px] text-muted">
                      {item.description || "No description"}
                    </p>
                    <div className="mt-1.5 flex flex-wrap items-center gap-2 text-[10.5px] text-muted">
                      <span>{num(item.counts?.messages ?? 0)} messages</span>
                      <span>·</span>
                      <span>{num(item.counts?.conversations ?? 0)} conversations</span>
                      <span>·</span>
                      <span>{num(item.counts?.evidence ?? 0)} evidence items</span>
                      <span>·</span>
                      <span>updated {relative(item.updated_at)}</span>
                    </div>
                  </button>
                  <div className="flex shrink-0 items-center gap-1">
                    {item.status === "archived" ? (
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={async () => {
                          await patch(`/api/cases/${item.id}`, { status: "active" });
                          await reload();
                        }}
                      >
                        Unarchive
                      </Button>
                    ) : (
                      <Button
                        size="sm"
                        variant="ghost"
                        title="Archive case"
                        onClick={async () => {
                          await post(`/api/cases/${item.id}/archive`);
                          await reload();
                          toast({ title: "Case archived", tone: "info" });
                        }}
                      >
                        <ArchiveRestore className="h-3.5 w-3.5" />
                      </Button>
                    )}
                    <Button size="sm" variant="primary" onClick={() => navigate(`/cases/${item.id}`)}>
                      Open <ArrowRight className="h-3.5 w-3.5" />
                    </Button>
                  </div>
                </article>
              ))
            )}

            <Panel title="Local evidence store" subtitle={diagnostics?.data_dir}>
              <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
                <Stat label="Database" value={bytes(diagnostics?.db_bytes)} icon={<HardDrive className="h-3.5 w-3.5" />} />
                <Stat label="Disk free" value={bytes(diagnostics?.disk_free_bytes)} icon={<HardDrive className="h-3.5 w-3.5" />} />
                <Stat label="Cases" value={num(diagnostics?.cases)} icon={<Database className="h-3.5 w-3.5" />} />
                <Stat label="Messages" value={num(diagnostics?.messages)} icon={<Database className="h-3.5 w-3.5" />} />
              </div>
              <p className="mt-2 flex items-start gap-1.5 text-[11px] leading-relaxed text-muted">
                <ShieldCheck className="mt-0.5 h-3.5 w-3.5 shrink-0 text-teal" />
                Originals are stored byte-identical under each case directory and re-verifiable
                at any time (Case management → verify integrity). No telemetry, no accounts, no
                automatic synchronisation.
              </p>
            </Panel>
          </div>

          <div className="space-y-3">
            <Panel title="System readiness">
              {diagnostics ? (
                <div className="space-y-2 text-[11.5px]">
                  <Row label="Engine" value={diagnostics.engine_version} tone="teal" />
                  <Row label="SQLite" value={`${diagnostics.sqlite} · FTS5 ${diagnostics.fts5 ? "on" : "off"}`} />
                  <Row label="Python sidecar" value={diagnostics.python} />
                  <Row label="Platform" value={diagnostics.platform} />
                  <Row
                    label="Local AI"
                    value={diagnostics.ai.ok ? `${diagnostics.ai.provider} (${diagnostics.ai.models.length} models)` : "not running"}
                    tone={diagnostics.ai.ok ? "teal" : "amber"}
                  />
                  <Row
                    label="Transcription"
                    value={diagnostics.transcription.available ? "engine available" : "no local model"}
                    tone={diagnostics.transcription.available ? "teal" : "amber"}
                  />
                  <Row
                    label="Media tools"
                    value={[
                      diagnostics.media_tools.ffprobe ? "ffprobe" : null,
                      diagnostics.media_tools.exiftool ? "exiftool" : null,
                      diagnostics.media_tools.pillow ? "Pillow" : null,
                    ]
                      .filter(Boolean)
                      .join(", ") || "python fallbacks"}
                  />
                  {!diagnostics.ai.ok && diagnostics.ai.error ? (
                    <p className="rounded-lg border border-amber/30 bg-amber/8 p-2 text-[10.5px] leading-relaxed text-amber">
                      {diagnostics.ai.error}
                    </p>
                  ) : null}
                </div>
              ) : (
                <Spinner />
              )}
            </Panel>

            <Panel title="How evidence is handled">
              <ol className="space-y-2 text-[11.5px] leading-relaxed text-muted">
                {[
                  "Create a case and record your authorisation declaration.",
                  "Import a WhatsApp TXT export or a media-inclusive ZIP.",
                  "Each original is hashed (SHA-256) and copied read-only.",
                  "Parsing keeps the original timestamp string plus a normalised UTC value.",
                  "Duplicates across snapshots are reconciled with provenance, never merged silently.",
                  "Every finding cites the evidence id and source line/row.",
                ].map((step, index) => (
                  <li key={step} className="flex gap-2">
                    <span className="mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center rounded-full border border-accent/40 bg-accent/10 text-[9px] text-accent">
                      {index + 1}
                    </span>
                    <span>{step}</span>
                  </li>
                ))}
              </ol>
            </Panel>
          </div>
        </div>
      </PageBody>

      <Dialog
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        title="Create investigation case"
        description="A case keeps its evidence, derived records, notes and reports separate from every other investigation."
        footer={
          <>
            <Button variant="ghost" onClick={() => setCreateOpen(false)}>
              Cancel
            </Button>
            <Button variant="primary" loading={busy} disabled={!form.name.trim() || !ack} onClick={() => void createCase()}>
              Create case
            </Button>
          </>
        }
      >
        {error ? <ErrorState error={error} /> : null}
        <div className="space-y-3">
          <Field label="Case name">
            <Input value={form.name} onChange={(event) => setForm({ ...form, name: event.target.value })} placeholder="e.g. Personal archive review — 2024" />
          </Field>
          <Field label="Description" hint="optional">
            <Textarea
              value={form.description}
              onChange={(event) => setForm({ ...form, description: event.target.value })}
              placeholder="Scope, purpose and any limits agreed with the owner."
            />
          </Field>
          <Field label="Examiner" hint="optional">
            <Input value={form.examiner} onChange={(event) => setForm({ ...form, examiner: event.target.value })} />
          </Field>
          <div className="rounded-xl border border-amber/30 bg-amber/8 p-3">
            <Checkbox
              checked={ack}
              onChange={setAck}
              label="I confirm I own this data or have explicit authorisation to examine it."
              hint="This declaration is stored with the case and written to the audit log. The application does not bypass encryption or acquire data from devices."
            />
          </div>
        </div>
      </Dialog>

      <Dialog
        open={restoreOpen}
        onClose={() => setRestoreOpen(false)}
        title="Restore an encrypted case backup"
        description="Backups are AES-256-GCM containers created by this application. Restoring creates a new case and never overwrites an existing one."
        footer={
          <>
            <Button variant="ghost" onClick={() => setRestoreOpen(false)}>
              Cancel
            </Button>
            <Button variant="primary" loading={busy} disabled={!restore.path || !restore.password} onClick={() => void restoreCase()}>
              Restore
            </Button>
          </>
        }
      >
        {error ? <ErrorState error={error} /> : null}
        <div className="space-y-3">
          <Field label="Backup file path">
            <Input value={restore.path} onChange={(event) => setRestore({ ...restore, path: event.target.value })} placeholder="C:\\Backups\\case-0001.wfsbak" />
          </Field>
          <Field label="Passphrase">
            <Input type="password" value={restore.password} onChange={(event) => setRestore({ ...restore, password: event.target.value })} />
          </Field>
          <Field label="New case name" hint="optional">
            <Input value={restore.name} onChange={(event) => setRestore({ ...restore, name: event.target.value })} />
          </Field>
        </div>
      </Dialog>
    </div>
  );
}

function Stat({ label, value, icon }: { label: string; value: string; icon: React.ReactNode }) {
  return (
    <div className="surface-muted px-2.5 py-2">
      <div className="flex items-center gap-1 text-[10px] uppercase tracking-[0.07em] text-muted">
        {icon}
        {label}
      </div>
      <p className="mt-0.5 text-[13px] font-semibold text-ink">{value}</p>
    </div>
  );
}

function Row({ label, value, tone = "default" }: { label: string; value: string; tone?: "default" | "teal" | "amber" }) {
  return (
    <div className="flex items-center justify-between gap-2 border-b border-line/50 pb-1.5 last:border-0">
      <span className="text-muted">{label}</span>
      <span className={tone === "teal" ? "text-teal" : tone === "amber" ? "text-amber" : "text-ink"}>{value}</span>
    </div>
  );
}

export function CaseDeleteButton({ caseId, onDeleted }: { caseId: string; onDeleted: () => void }) {
  const [confirming, setConfirming] = React.useState(false);
  return (
    <>
      <Button variant="danger" size="sm" onClick={() => setConfirming(true)}>
        <Trash2 className="h-3.5 w-3.5" /> Delete case
      </Button>
      <Dialog
        open={confirming}
        onClose={() => setConfirming(false)}
        title="Delete this case?"
        description="The case database records and its directory are removed from this computer. This cannot be undone; export a backup first if the case may be needed."
        footer={
          <>
            <Button variant="ghost" onClick={() => setConfirming(false)}>
              Cancel
            </Button>
            <Button
              variant="danger"
              onClick={() => {
                void del(`/api/cases/${caseId}`).then(() => {
                  setConfirming(false);
                  onDeleted();
                });
              }}
            >
              Delete permanently
            </Button>
          </>
        }
      >
        <p className="text-[12px] text-muted">
          Evidence originals inside the case folder are also removed. Files you imported from
          elsewhere on the machine are not touched.
        </p>
      </Dialog>
    </>
  );
}
