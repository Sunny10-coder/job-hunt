import { AlertTriangle, CheckCircle2, FileArchive, FileText, FolderInput, ShieldCheck, Sparkles, Upload, XCircle } from "lucide-react";
import * as React from "react";
import { PageBody, PageHeader } from "@/components/layout/PageHeader";
import {
  Badge,
  Button,
  Checkbox,
  EmptyState,
  ErrorState,
  Field,
  Panel,
  Progress,
  Select,
  Spinner,
  Tabs,
} from "@/components/ui/primitives";
import { get, post } from "@/lib/api";
import { bytes, dateTime, num } from "@/lib/format";
import { useCase } from "@/hooks/useCaseContext";
import { useApi, useJob } from "@/hooks/useApi";
import { useApp } from "@/stores/app";
import type { Evidence, ImportJob } from "@/types";

interface Quality {
  evidence_id: string;
  original_name: string;
  source_type: string;
  sha256: string;
  message_count: number;
  date_order: string | null;
  date_order_confidence: number | null;
  parse_confidence: number | null;
  language: string | null;
  encoding: string | null;
  duplicates: number;
  unresolved_lines: number;
  ambiguous_timestamps: number;
  media_linked: number;
  media_unlinked: number;
  system_messages: number;
  deleted_markers: number;
  edited_markers: number;
  date_order_reason: string;
  issues: { severity: string; code: string; message: string; line_no: number | null }[];
}

const TIMEZONES = [
  "UTC",
  "Asia/Kolkata",
  "Asia/Dubai",
  "Asia/Riyadh",
  "Asia/Karachi",
  "Asia/Colombo",
  "Asia/Singapore",
  "Europe/London",
  "Europe/Berlin",
  "Europe/Paris",
  "America/New_York",
  "America/Chicago",
  "America/Los_Angeles",
  "Australia/Sydney",
];

export function ImportCenter() {
  const { caseId, caseData } = useCase();
  const toast = useApp((state) => state.toast);
  const [paths, setPaths] = React.useState<string[]>([]);
  const [manual, setManual] = React.useState("");
  const [options, setOptions] = React.useState({
    source_timezone: "UTC",
    date_order: "auto",
    force: false,
    keep_copy: true,
    license_acknowledged: false,
  });
  const [jobId, setJobId] = React.useState<string | null>(null);
  const [error, setError] = React.useState<string | null>(null);
  const [selectedEvidence, setSelectedEvidence] = React.useState<string | null>(null);
  const [tab, setTab] = React.useState<"import" | "quality">("import");
  const [dragging, setDragging] = React.useState(false);

  const evidenceApi = useApi<Evidence[]>(caseId ? `/api/cases/${caseId}/evidence` : null, [caseId]);
  const qualityApi = useApi<Quality>(
    selectedEvidence ? `/api/cases/${caseId}/evidence/${selectedEvidence}/quality` : null,
    [selectedEvidence],
  );

  const { job } = useJob(jobId, (status) => {
    if (status === "done") {
      toast({ title: "Import finished", tone: "success" });
      evidenceApi.reload();
      setTab("quality");
    } else if (status === "failed") {
      toast({ title: "Import finished with errors", tone: "error" });
      evidenceApi.reload();
    }
  });

  const pickFiles = async () => {
    setError(null);
    if (typeof window !== "undefined" && window.__TAURI_INTERNALS__) {
      try {
        const { invoke } = await import("@tauri-apps/api/core");
        const picked = await invoke<string[]>("pick_evidence_files");
        if (picked.length) setPaths((current) => [...current, ...picked]);
        return;
      } catch (err) {
        setError((err as Error).message);
      }
    }
    setError(
      "Native file picking is available in the desktop build. In the browser preview, paste absolute paths below or load the synthetic sample dataset.",
    );
  };

  const startImport = async () => {
    setError(null);
    const list = paths.length ? paths : manual.split("\n").map((line) => line.trim()).filter(Boolean);
    if (!list.length) {
      setError("Add at least one evidence file path.");
      return;
    }
    if (!options.license_acknowledged) {
      setError("Confirm the authorisation declaration before importing.");
      return;
    }
    try {
      const job = await post<{ job_id: string }>(`/api/cases/${caseId}/import`, {
        paths: list,
        options,
      });
      setJobId(job.job_id);
      setPaths([]);
      setManual("");
      toast({ title: "Import started", description: `${list.length} file(s) queued`, tone: "info" });
    } catch (err) {
      setError((err as Error).message);
    }
  };

  const loadSample = async () => {
    setError(null);
    try {
      const job = await post<{ job_id: string }>(`/api/cases/${caseId}/import-sample`, { options });
      setJobId(job.job_id);
      toast({ title: "Synthetic dataset importing", description: "No real conversations are included.", tone: "info" });
    } catch (err) {
      setError((err as Error).message);
    }
  };

  return (
    <div className="flex h-full min-h-0 flex-col">
      <PageHeader
        title="Evidence import centre"
        description="Import WhatsApp TXT exports, media-inclusive ZIP archives, standalone media or accessible unencrypted SQLite databases. Originals are hashed and copied; nothing is modified."
        badges={<Badge tone="teal"><ShieldCheck className="h-3 w-3" /> SHA-256 at ingest</Badge>}
        actions={
          <Tabs
            value={tab}
            onChange={setTab}
            tabs={[
              { value: "import", label: "Import" },
              { value: "quality", label: "Import quality" },
            ]}
          />
        }
      />
      <PageBody className="p-4">
        {error ? <ErrorState error={error} /> : null}
        {tab === "import" ? (
          <div className="grid gap-3 xl:grid-cols-[minmax(0,1.3fr)_minmax(0,1fr)]">
            <div className="space-y-3">
              <Panel title="Evidence files">
                <div
                  onDragOver={(event) => {
                    event.preventDefault();
                    setDragging(true);
                  }}
                  onDragLeave={() => setDragging(false)}
                  onDrop={(event) => {
                    event.preventDefault();
                    setDragging(false);
                    const dropped = Array.from(event.dataTransfer.files)
                      .map((file) => (file as File & { path?: string }).path)
                      .filter((value): value is string => Boolean(value));
                    if (dropped.length) setPaths((current) => [...current, ...dropped]);
                    else setError("The browser cannot read full paths from a drop. Use the desktop build, or paste paths below.");
                  }}
                  className={`flex flex-col items-center justify-center gap-2 rounded-xl border border-dashed px-4 py-8 text-center transition ${
                    dragging ? "border-accent bg-accent/8" : "border-line bg-elevated/40"
                  }`}
                >
                  <FolderInput className="h-7 w-7 text-muted" />
                  <p className="text-[12.5px] font-medium text-ink">Drop evidence files here</p>
                  <p className="max-w-md text-[11px] leading-relaxed text-muted">
                    WhatsApp export files are usually named <span className="mono">WhatsApp Chat with ….txt</span> or{" "}
                    <span className="mono">…​.zip</span>. ZIP archives are validated (path traversal, symlinks,
                    decompression bombs) before extraction.
                  </p>
                  <div className="mt-1 flex gap-1.5">
                    <Button size="sm" variant="primary" onClick={() => void pickFiles()}>
                      <Upload className="h-3.5 w-3.5" /> Choose files
                    </Button>
                    <Button size="sm" variant="ghost" onClick={() => void loadSample()}>
                      <Sparkles className="h-3.5 w-3.5" /> Load sample dataset
                    </Button>
                  </div>
                </div>

                <Field label="File paths" hint="one absolute path per line">
                  <textarea
                    value={manual}
                    onChange={(event) => setManual(event.target.value)}
                    rows={3}
                    placeholder={"C:\\Evidence\\WhatsApp Chat with Alex.txt\nC:\\Evidence\\WhatsApp Chat with Alex.zip"}
                    className="field font-mono text-[11.5px]"
                  />
                </Field>

                {paths.length > 0 ? (
                  <div className="mt-2 space-y-1">
                    {paths.map((path) => (
                      <div key={path} className="flex items-center gap-2 rounded-lg border border-line bg-elevated/60 px-2 py-1.5">
                        {path.toLowerCase().endsWith(".zip") ? (
                          <FileArchive className="h-3.5 w-3.5 text-teal" />
                        ) : (
                          <FileText className="h-3.5 w-3.5 text-accent" />
                        )}
                        <span className="mono min-w-0 flex-1 truncate text-[11px] text-ink">{path}</span>
                        <Button size="icon" variant="ghost" onClick={() => setPaths(paths.filter((item) => item !== path))}>
                          <XCircle className="h-3.5 w-3.5" />
                        </Button>
                      </div>
                    ))}
                  </div>
                ) : null}
              </Panel>

              <Panel title="Parsing options">
                <div className="grid gap-2 sm:grid-cols-2">
                  <Field label="Source timezone" hint="exports have no timezone">
                    <Select value={options.source_timezone} onChange={(event) => setOptions({ ...options, source_timezone: event.target.value })}>
                      {TIMEZONES.map((zone) => (
                        <option key={zone} value={zone}>
                          {zone}
                        </option>
                      ))}
                    </Select>
                  </Field>
                  <Field label="Date order" hint="auto = proven from data">
                    <Select value={options.date_order} onChange={(event) => setOptions({ ...options, date_order: event.target.value })}>
                      <option value="auto">Auto-detect</option>
                      <option value="mdy">Month first (12/31/24)</option>
                      <option value="dmy">Day first (31/12/24)</option>
                    </Select>
                  </Field>
                </div>
                <div className="mt-2 grid gap-2 sm:grid-cols-2">
                  <Checkbox
                    checked={options.keep_copy}
                    onChange={(value) => setOptions({ ...options, keep_copy: value })}
                    label="Copy originals into the case folder"
                    hint="Recommended: the case stays self-contained and hash-verifiable."
                  />
                  <Checkbox
                    checked={options.force}
                    onChange={(value) => setOptions({ ...options, force: value })}
                    label="Re-import identical files"
                    hint="By default a file with a known SHA-256 is never parsed twice."
                  />
                </div>
                <div className="mt-2 rounded-xl border border-amber/30 bg-amber/8 p-3">
                  <Checkbox
                    checked={options.license_acknowledged}
                    onChange={(value) => setOptions({ ...options, license_acknowledged: value })}
                    label="I am authorised to examine these files."
                    hint="The application does not decrypt Crypt12/14/15 databases or acquire data from devices."
                  />
                </div>
                <div className="mt-3 flex items-center justify-between">
                  <p className="text-[11px] text-muted">
                    {caseData ? `Target case: ${caseData.name}` : ""}
                  </p>
                  <Button variant="primary" onClick={() => void startImport()}>
                    <Upload className="h-3.5 w-3.5" /> Start import
                  </Button>
                </div>
              </Panel>

              {job ? <JobProgress job={job} /> : null}
            </div>

            <div className="space-y-3">
              <Panel title="Imported evidence" dense actions={<Button size="sm" variant="ghost" onClick={evidenceApi.reload}>Refresh</Button>}>
                {evidenceApi.loading && !evidenceApi.data ? <Spinner /> : null}
                {evidenceApi.error ? <ErrorState error={evidenceApi.error} onRetry={evidenceApi.reload} /> : null}
                <div className="divide-y divide-line/60">
                  {(evidenceApi.data ?? []).map((item) => (
                    <button
                      key={item.id}
                      onClick={() => {
                        setSelectedEvidence(item.id);
                        setTab("quality");
                      }}
                      className="w-full px-3 py-2 text-left hover:bg-elevated/60"
                    >
                      <div className="flex items-center justify-between gap-2">
                        <span className="truncate text-[12px] text-ink">{item.original_name}</span>
                        <Badge tone={item.status === "imported" ? "teal" : item.status === "failed" ? "danger" : "amber"}>
                          {item.status}
                        </Badge>
                      </div>
                      <p className="mt-0.5 text-[10.5px] text-muted">
                        {num(item.message_count)} messages · {bytes(item.size_bytes)} · {item.date_order ?? "n/a"} order ·{" "}
                        {item.language ?? "unknown"}
                      </p>
                      <p className="mono truncate text-[10px] text-muted/80" title={item.sha256}>
                        {item.sha256}
                      </p>
                    </button>
                  ))}
                  {(evidenceApi.data ?? []).length === 0 ? (
                    <EmptyState title="No evidence yet" description="Imported files and their hashes appear here." />
                  ) : null}
                </div>
              </Panel>

              <Panel title="What the parser records">
                <ul className="space-y-1.5 text-[11.5px] leading-relaxed text-muted">
                  <li>• Original timestamp string and normalised UTC value per message.</li>
                  <li>• Source line/row reference so any finding can be traced to the artifact.</li>
                  <li>• Parse confidence per record; unresolved lines are reported, never dropped.</li>
                  <li>• Detected date order with a confidence and the reason it was chosen.</li>
                  <li>• Multiline bodies, emoji, Malayalam / Hindi / Tamil / Arabic script, URLs and phone numbers.</li>
                  <li>• Deleted and edited markers as indicators, never reconstructed text.</li>
                </ul>
              </Panel>
            </div>
          </div>
        ) : (
          <div className="grid gap-3 xl:grid-cols-[280px_minmax(0,1fr)]">
            <Panel title="Evidence" dense>
              <div className="divide-y divide-line/60">
                {(evidenceApi.data ?? []).map((item) => (
                  <button
                    key={item.id}
                    onClick={() => setSelectedEvidence(item.id)}
                    className={`w-full px-3 py-2 text-left text-[12px] hover:bg-elevated/60 ${
                      selectedEvidence === item.id ? "bg-elevated text-ink" : "text-muted"
                    }`}
                  >
                    {item.original_name}
                  </button>
                ))}
              </div>
            </Panel>

            <Panel title="Import quality report" subtitle={qualityApi.data?.original_name}>
              {qualityApi.loading ? <Spinner /> : null}
              {qualityApi.error ? <ErrorState error={qualityApi.error} onRetry={qualityApi.reload} /> : null}
              {qualityApi.data ? (
                <div className="space-y-3">
                  <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
                    <Metric label="Messages" value={num(qualityApi.data.message_count)} />
                    <Metric label="Parse confidence" value={`${Math.round((qualityApi.data.parse_confidence ?? 0) * 100)}%`} />
                    <Metric label="Duplicates skipped" value={num(qualityApi.data.duplicates)} />
                    <Metric label="Unresolved lines" value={num(qualityApi.data.unresolved_lines)} tone={qualityApi.data.unresolved_lines ? "amber" : "default"} />
                    <Metric label="Date order" value={qualityApi.data.date_order ?? "n/a"} />
                    <Metric label="Order confidence" value={`${Math.round((qualityApi.data.date_order_confidence ?? 0) * 100)}%`} />
                    <Metric label="Encoding" value={qualityApi.data.encoding ?? "utf-8"} />
                    <Metric label="Language hint" value={qualityApi.data.language ?? "unknown"} />
                    <Metric label="Media linked" value={num(qualityApi.data.media_linked)} />
                    <Metric label="Media not linked" value={num(qualityApi.data.media_unlinked)} tone={qualityApi.data.media_unlinked ? "amber" : "default"} />
                    <Metric label="Deleted markers" value={num(qualityApi.data.deleted_markers)} />
                    <Metric label="Edited markers" value={num(qualityApi.data.edited_markers)} />
                  </div>

                  <div className="rounded-xl border border-line bg-elevated/50 p-3 text-[11.5px] leading-relaxed text-muted">
                    <p className="flex items-center gap-1.5 text-ink">
                      <CheckCircle2 className="h-3.5 w-3.5 text-teal" /> Evidence integrity
                    </p>
                    <p className="mono mt-1 break-all text-[10.5px]">{qualityApi.data.sha256}</p>
                    <p className="mt-1">
                      Date order decided by {qualityApi.data.date_order_reason || "the import configuration"}.
                      {qualityApi.data.ambiguous_timestamps > 0
                        ? ` ${qualityApi.data.ambiguous_timestamps} timestamps fell in a DST-transition window and are flagged.`
                        : ""}
                    </p>
                  </div>

                  {qualityApi.data.issues.length > 0 ? (
                    <div>
                      <p className="section-title mb-1">Parser notes</p>
                      <div className="space-y-1">
                        {qualityApi.data.issues.map((issue, index) => (
                          <div key={index} className="flex items-start gap-2 rounded-lg border border-amber/25 bg-amber/5 px-2 py-1.5">
                            <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-amber" />
                            <div className="min-w-0">
                              <p className="text-[11.5px] text-ink">{issue.message}</p>
                              <p className="text-[10px] text-muted">
                                {issue.code}
                                {issue.line_no ? ` · line ${issue.line_no}` : ""}
                              </p>
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  ) : null}
                </div>
              ) : (
                <EmptyState title="Select an evidence item" description="The quality report shows parse confidence, date-order reasoning and any unresolved records." />
              )}
            </Panel>
          </div>
        )}
      </PageBody>
    </div>
  );
}

function Metric({ label, value, tone = "default" }: { label: string; value: string; tone?: "default" | "amber" }) {
  return (
    <div className="surface-muted px-2.5 py-2">
      <p className="kpi-label">{label}</p>
      <p className={`mt-0.5 text-[13px] font-semibold ${tone === "amber" ? "text-amber" : "text-ink"}`}>{value}</p>
    </div>
  );
}

function JobProgress({ job }: { job: ImportJob }) {
  return (
    <Panel title="Import progress" subtitle={`${job.stage} · ${job.status}`}>
      <Progress value={job.progress} />
      <div className="mt-1.5 flex items-center justify-between text-[11px] text-muted">
        <span>{Math.round(job.progress * 100)}% complete</span>
        <span>{job.finished_at ? `finished ${dateTime(job.finished_at)}` : "running…"}</span>
      </div>
      {job.error ? (
        <p className="mt-2 rounded-lg border border-danger/30 bg-danger/8 p-2 text-[11px] text-danger">{job.error}</p>
      ) : null}
      <div className="mt-2 max-h-52 space-y-1 overflow-y-auto scroll-thin">
        {job.log.map((entry, index) => (
          <p key={index} className="mono text-[10.5px] text-muted">
            <span className="text-accent">{entry.stage}</span> {entry.message}
          </p>
        ))}
        {job.errors.map((entry, index) => (
          <p key={`error-${index}`} className="mono text-[10.5px] text-danger">
            {entry.code}: {entry.message}
          </p>
        ))}
      </div>
      {job.status === "done" ? (
        <p className="mt-2 flex items-center gap-1.5 text-[11px] text-teal">
          <CheckCircle2 className="h-3.5 w-3.5" /> Search index built and dashboards refreshed.
        </p>
      ) : null}
    </Panel>
  );
}

export function useEvidencePaths(caseId: string) {
  return useApi<Evidence[]>(caseId ? `/api/cases/${caseId}/evidence` : null, [caseId]);
}

export async function refreshEvidence(caseId: string): Promise<Evidence[]> {
  return get<Evidence[]>(`/api/cases/${caseId}/evidence`);
}
