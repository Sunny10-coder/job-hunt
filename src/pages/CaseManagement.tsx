import { ArchiveRestore, Copy, Download, FileCheck2, FolderOpen, KeyRound, Save, ShieldCheck } from "lucide-react";
import * as React from "react";
import { useNavigate } from "react-router-dom";
import { PageHeader } from "@/components/layout/PageHeader";
import { Dialog } from "@/components/ui/dialog";
import { Badge, Button, EmptyState, ErrorState, Field, Input, Panel, Spinner, Tabs, Textarea } from "@/components/ui/primitives";
import { apiUrl, get, patch, post } from "@/lib/api";
import { isDesktop, revealPath } from "@/lib/native";
import { bytes, dateTime, num } from "@/lib/format";
import { useApi } from "@/hooks/useApi";
import { useCase } from "@/hooks/useCaseContext";
import { useApp } from "@/stores/app";
import { CaseDeleteButton } from "@/pages/Welcome";
import type { CaseSummary, Evidence } from "@/types";

type Tab = "overview" | "notes" | "audit";

export function CaseManagement() {
  const { caseId, caseData, reload: reloadCase } = useCase();
  const navigate = useNavigate();
  const toast = useApp((state) => state.toast);
  const [tab, setTab] = React.useState<Tab>("overview");
  const [form, setForm] = React.useState({ name: "", description: "", examiner: "", authorization_statement: "" });
  const [note, setNote] = React.useState("");
  const [busy, setBusy] = React.useState(false);
  const [verify, setVerify] = React.useState<{ evidence_id: string; original_name: string; expected_sha256: string; actual_sha256: string | null; state: string }[] | null>(null);
  const [backupOpen, setBackupOpen] = React.useState(false);
  const [passphrase, setPassphrase] = React.useState("");
  const [backupResult, setBackupResult] = React.useState<{ path: string; sha256: string } | null>(null);

  React.useEffect(() => {
    if (caseData) {
      setForm({
        name: caseData.name,
        description: caseData.description,
        examiner: caseData.examiner,
        authorization_statement: caseData.authorization_statement,
      });
    }
  }, [caseData]);

  const evidenceApi = useApi<Evidence[]>(caseId ? `/api/cases/${caseId}/evidence` : null, [caseId]);
  const notesApi = useApi<{ id: string; body: string; created_at: string; author: string; message_body?: string }[]>(caseId ? `/api/cases/${caseId}/notes` : null, [caseId]);
  const bookmarksApi = useApi<{ id: string; label: string; body: string; sent_at_utc: string; conversation_title: string }[]>(caseId ? `/api/cases/${caseId}/bookmarks` : null, [caseId]);
  const auditApi = useApi<{ id: string; at: string; action: string; actor: string; detail: Record<string, unknown> }[]>(caseId ? `/api/cases/${caseId}/audit` : null, [caseId]);
  const custodyApi = useApi<{ at: string; action: string; detail: Record<string, unknown> }[]>(caseId ? `/api/cases/${caseId}/custody` : null, [caseId]);
  const manifestApi = useApi<Record<string, unknown>>(caseId ? `/api/cases/${caseId}/manifest` : null, [caseId]);

  const save = async () => {
    setBusy(true);
    try {
      await patch(`/api/cases/${caseId}`, form);
      reloadCase();
      toast({ title: "Case details saved", tone: "success" });
    } finally {
      setBusy(false);
    }
  };

  const verifyNow = async () => {
    setBusy(true);
    try {
      setVerify(await post(`/api/cases/${caseId}/evidence/verify`));
      const allOk = (await get<{ evidence_id: string }[]>(`/api/cases/${caseId}/evidence`)).length > 0;
      toast({ title: allOk ? "Integrity check complete" : "Nothing to verify", tone: "success" });
    } finally {
      setBusy(false);
    }
  };

  const runBackup = async () => {
    setBusy(true);
    try {
      const result = await post<{ path: string; sha256: string }>(`/api/cases/${caseId}/backup`, { password: passphrase });
      setBackupResult(result);
      toast({ title: "Encrypted backup created", tone: "success" });
    } catch (err) {
      toast({ title: "Backup failed", description: (err as Error).message, tone: "error" });
    } finally {
      setBusy(false);
    }
  };

  const duplicate = async () => {
    setBusy(true);
    try {
      const created = await post<CaseSummary>(`/api/cases/${caseId}/duplicate`, {});
      toast({ title: "Case duplicated", description: `CASE-${String(created.case_number).padStart(4, "0")}`, tone: "success" });
      navigate(`/cases/${created.id}`);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex h-full min-h-0 flex-col">
      <PageHeader
        title="Case management"
        description="Case identity, authorisation record, evidence inventory, annotations and the audit trail that supports chain of custody."
        badges={caseData ? <Badge tone="accent">CASE-{String(caseData.case_number).padStart(4, "0")}</Badge> : null}
        actions={
          <>
            <Tabs value={tab} onChange={setTab} tabs={[{ value: "overview", label: "Overview" }, { value: "notes", label: "Annotations" }, { value: "audit", label: "Audit" }]} />
            <Button variant="ghost" onClick={() => void duplicate()} loading={busy}>
              <Copy className="h-3.5 w-3.5" /> Duplicate
            </Button>
            <Button variant="ghost" onClick={() => setBackupOpen(true)}>
              <KeyRound className="h-3.5 w-3.5" /> Backup
            </Button>
          </>
        }
      />

      <div className="min-h-0 flex-1 overflow-y-auto p-4 scroll-thin">
        {tab === "overview" ? (
          <div className="grid gap-3 xl:grid-cols-[minmax(0,1fr)_360px]">
            <div className="space-y-3">
              <Panel title="Case details" actions={<Button size="sm" variant="primary" loading={busy} onClick={() => void save()}><Save className="h-3.5 w-3.5" /> Save</Button>}>
                <div className="space-y-2">
                  <Field label="Name">
                    <Input value={form.name} onChange={(event) => setForm({ ...form, name: event.target.value })} />
                  </Field>
                  <Field label="Description">
                    <Textarea value={form.description} onChange={(event) => setForm({ ...form, description: event.target.value })} />
                  </Field>
                  <Field label="Examiner">
                    <Input value={form.examiner} onChange={(event) => setForm({ ...form, examiner: event.target.value })} />
                  </Field>
                  <Field label="Authorisation declaration">
                    <Textarea value={form.authorization_statement} onChange={(event) => setForm({ ...form, authorization_statement: event.target.value })} />
                  </Field>
                  <div className="flex items-center justify-between">
                    <p className="text-[10.5px] text-muted">Created {dateTime(caseData?.created_at)} · updated {dateTime(caseData?.updated_at)}</p>
                    {caseData ? <CaseDeleteButton caseId={caseId} onDeleted={() => navigate("/")} /> : null}
                  </div>
                </div>
              </Panel>

              <Panel
                title="Evidence inventory"
                actions={
                  <Button size="sm" variant="ghost" loading={busy} onClick={() => void verifyNow()}>
                    <FileCheck2 className="h-3.5 w-3.5" /> Verify integrity
                  </Button>
                }
                dense
              >
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>File</th>
                      <th>Type</th>
                      <th>Messages</th>
                      <th>Bytes</th>
                      <th>SHA-256</th>
                      <th>Imported</th>
                      <th>Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(evidenceApi.data ?? []).map((item) => {
                      const check = verify?.find((row) => row.evidence_id === item.id);
                      return (
                        <tr key={item.id}>
                          <td className="text-ink">{item.original_name}</td>
                          <td>{item.source_type}</td>
                          <td>{num(item.message_count)}</td>
                          <td>{bytes(item.size_bytes)}</td>
                          <td className="mono text-[10px]" title={item.sha256}>{item.sha256.slice(0, 24)}…</td>
                          <td className="text-[10.5px] text-muted">{dateTime(item.imported_at)}</td>
                          <td>
                            {check ? (
                              <Badge tone={check.state === "ok" ? "teal" : "danger"}>{check.state}</Badge>
                            ) : (
                              <Badge>{item.status}</Badge>
                            )}
                          </td>
                        </tr>
                      );
                    })}
                    {(evidenceApi.data ?? []).length === 0 ? (
                      <tr>
                        <td colSpan={7}>
                          <EmptyState title="No evidence" description="Import an export to begin." />
                        </td>
                      </tr>
                    ) : null}
                  </tbody>
                </table>
              </Panel>

              <Panel title="Bookmarked findings" dense>
                <div className="divide-y divide-line/60">
                  {(bookmarksApi.data ?? []).map((bookmark) => (
                    <div key={bookmark.id} className="px-3 py-2">
                      <p className="text-[11px] text-amber">{bookmark.label || "bookmarked"}</p>
                      <p dir="auto" className="line-clamp-2 text-[11.5px] text-ink">{bookmark.body}</p>
                      <p className="text-[10px] text-muted">{bookmark.conversation_title} · {dateTime(bookmark.sent_at_utc)}</p>
                    </div>
                  ))}
                  {(bookmarksApi.data ?? []).length === 0 ? <p className="p-3 text-[11px] text-muted">No bookmarks recorded.</p> : null}
                </div>
              </Panel>
            </div>

            <div className="space-y-3">
              <Panel title="Integrity & hashes">
                <div className="space-y-1.5 text-[11px]">
                  {verify ? (
                    verify.map((row) => (
                      <div key={row.evidence_id} className="rounded-lg border border-line bg-elevated/50 p-2">
                        <p className="text-[11.5px] text-ink">{row.original_name}</p>
                        <p className="mono truncate text-[10px] text-muted">expected {row.expected_sha256}</p>
                        <p className="mono truncate text-[10px] text-muted">actual&nbsp;&nbsp; {row.actual_sha256 ?? "missing"}</p>
                        <Badge tone={row.state === "ok" ? "teal" : "danger"}>{row.state}</Badge>
                      </div>
                    ))
                  ) : (
                    <p className="text-muted">Run an integrity check to re-hash every stored original and compare it with the ingestion hash.</p>
                  )}
                </div>
              </Panel>

              <Panel title="Case manifest" dense>
                <div className="p-2">
                  <pre className="mono max-h-52 overflow-auto text-[10px] leading-relaxed text-muted scroll-thin">
                    {manifestApi.data ? JSON.stringify(manifestApi.data, null, 2) : "loading…"}
                  </pre>
                  <Button size="sm" variant="ghost" className="mt-1 w-full" onClick={() => window.open(apiUrl(`/api/cases/${caseId}/manifest`), "_blank")}>
                    <Download className="h-3.5 w-3.5" /> Open manifest.json
                  </Button>
                </div>
              </Panel>

              <Panel title="Chain of custody" dense>
                <div className="max-h-64 space-y-1 overflow-y-auto p-2 scroll-thin">
                  {(custodyApi.data ?? []).map((entry, index) => (
                    <div key={index} className="border-b border-line/50 pb-1 text-[10.5px] last:border-0">
                      <p className="text-ink">{entry.action}</p>
                      <p className="text-muted">{dateTime(entry.at)}</p>
                    </div>
                  ))}
                  {(custodyApi.data ?? []).length === 0 ? <p className="text-[11px] text-muted">No custody events yet.</p> : null}
                </div>
              </Panel>
            </div>
          </div>
        ) : tab === "notes" ? (
          <div className="grid gap-3 lg:grid-cols-[minmax(0,1fr)_360px]">
            <Panel title="Investigation notes">
              <div className="mb-3 space-y-2">
                <Field label="New note">
                  <Textarea value={note} onChange={(event) => setNote(event.target.value)} placeholder="Observation, hypothesis or follow-up action…" />
                </Field>
                <div className="flex justify-end">
                  <Button
                    variant="primary"
                    disabled={!note.trim()}
                    onClick={async () => {
                      await post(`/api/cases/${caseId}/notes`, { body: note });
                      setNote("");
                      notesApi.reload();
                      toast({ title: "Note added", tone: "success" });
                    }}
                  >
                    Add note
                  </Button>
                </div>
              </div>
              <div className="space-y-2">
                {(notesApi.data ?? []).map((item) => (
                  <div key={item.id} className="rounded-lg border border-line bg-elevated/50 p-2.5">
                    <p dir="auto" className="whitespace-pre-wrap text-[12px] text-ink">{item.body}</p>
                    <p className="mt-1 text-[10px] text-muted">{item.author} · {dateTime(item.created_at)}</p>
                  </div>
                ))}
                {(notesApi.data ?? []).length === 0 ? <EmptyState title="No notes" description="Notes are case records and appear in reports." /> : null}
              </div>
            </Panel>
            <Panel title="Evidence handling" dense>
              <ul className="space-y-2 p-3 text-[11px] leading-relaxed text-muted">
                <li className="flex gap-1.5"><ShieldCheck className="mt-0.5 h-3.5 w-3.5 shrink-0 text-teal" /> Originals are copied byte-identically; the SHA-256 is recorded at ingestion and can be re-verified.</li>
                <li className="flex gap-1.5"><ArchiveRestore className="mt-0.5 h-3.5 w-3.5 shrink-0 text-accent" /> Derived records keep evidence id + source reference; deleting annotations never alters evidence.</li>
                <li>Encrypted backups (AES-256-GCM, scrypt-derived key) can be restored into a new case without overwriting anything.</li>
                <li>Uninstall does not delete case data: cases live under the user data directory, separate from the application binaries.</li>
              </ul>
            </Panel>
          </div>
        ) : (
          <div className="grid gap-3 lg:grid-cols-[minmax(0,1fr)_320px]">
            <Panel title="Audit log" dense>
              <div className="divide-y divide-line/60">
                {(auditApi.data ?? []).map((entry) => (
                  <div key={entry.id} className="px-3 py-1.5">
                    <div className="flex items-center justify-between gap-2">
                      <span className="mono text-[11px] text-accent">{entry.action}</span>
                      <span className="text-[10px] text-muted">{dateTime(entry.at)}</span>
                    </div>
                    <p className="text-[10px] text-muted">{entry.actor}</p>
                    {Object.keys(entry.detail).length > 0 ? (
                      <p className="mono mt-0.5 line-clamp-2 text-[10px] text-muted/80">{JSON.stringify(entry.detail)}</p>
                    ) : null}
                  </div>
                ))}
              </div>
            </Panel>
            <Panel title="Retention">
              <p className="text-[11.5px] leading-relaxed text-muted">
                Audit entries are retained according to the retention setting in Settings → Forensic. Evidence content is
                never written to diagnostic logs; only identifiers and hashes are recorded.
              </p>
            </Panel>
          </div>
        )}
      </div>

      <Dialog
        open={backupOpen}
        onClose={() => { setBackupOpen(false); setPassphrase(""); setBackupResult(null); }}
        title="Create encrypted case backup"
        description="AES-256-GCM with a scrypt-derived key. The archive contains the case directory and every case-scoped database row."
        footer={
          <>
            <Button variant="ghost" onClick={() => { setBackupOpen(false); setPassphrase(""); setBackupResult(null); }}>Close</Button>
            <Button variant="primary" loading={busy} disabled={passphrase.length < 8} onClick={() => void runBackup()}>
              Create backup
            </Button>
          </>
        }
      >
        <div className="space-y-3">
          <Field label="Passphrase" hint="at least 8 characters">
            <Input type="password" value={passphrase} onChange={(event) => setPassphrase(event.target.value)} />
          </Field>
          {backupResult ? (
            <div className="rounded-lg border border-teal/30 bg-teal/8 p-2 text-[11px]">
              <p className="text-teal">Backup written</p>
              <p className="mono mt-1 break-all text-[10.5px] text-ink">{backupResult.path}</p>
              <p className="mono mt-1 break-all text-[10px] text-muted">sha256 {backupResult.sha256}</p>
              {isDesktop() ? (
                <Button
                  size="sm"
                  variant="ghost"
                  className="mt-2"
                  onClick={() => void revealPath(backupResult.path).then((ok) => { if (!ok) toast({ title: "Could not open the backup folder", tone: "error" }); })}
                >
                  <FolderOpen className="h-3 w-3" /> Show in folder
                </Button>
              ) : null}
            </div>
          ) : null}
          <p className="text-[10.5px] leading-relaxed text-muted">
            Store the passphrase safely: it is never written to disk and cannot be recovered. Restore with
            Cases → Restore backup.
          </p>
        </div>
      </Dialog>
      {evidenceApi.loading ? <Spinner /> : null}
      {evidenceApi.error ? <ErrorState error={evidenceApi.error} onRetry={evidenceApi.reload} /> : null}
    </div>
  );
}
