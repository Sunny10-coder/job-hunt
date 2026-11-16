import { CheckCircle2, Cpu, Database, HardDrive, KeyRound, RotateCw, ShieldCheck, Sparkles } from "lucide-react";
import * as React from "react";
import { PageHeader } from "@/components/layout/PageHeader";
import { Badge, Button, EmptyState, ErrorState, Field, Input, Panel, Select, Spinner, Switch, Tabs } from "@/components/ui/primitives";
import { get, patch } from "@/lib/api";
import { bytes, num } from "@/lib/format";
import { clearApiKey, hasStoredApiKey, isDesktop, restartEngine, saveApiKey } from "@/lib/native";
import { useApi } from "@/hooks/useApi";
import { useApp } from "@/stores/app";
import type { Settings } from "@/types";

interface Diagnostics {
  engine_version: string;
  python: string;
  platform: string;
  sqlite: string;
  fts5: boolean;
  data_dir: string;
  db_path: string;
  db_bytes: number;
  disk_free_bytes: number;
  disk_total_bytes: number;
  cases: number;
  messages: number;
  ai: { ok: boolean; provider: string | null; models: string[]; error?: string; hint?: string };
  transcription: { available: boolean; whisper_cpp: string | null; faster_whisper: boolean; hint: string };
  media_tools: { exiftool: string | null; ffprobe: string | null; ffmpeg: string | null; pillow: boolean };
  audit_entries: number;
}

type Tab = "appearance" | "forensic" | "ai" | "storage" | "diagnostics";

const TIMEZONES = ["UTC", "Asia/Kolkata", "Asia/Dubai", "Asia/Riyadh", "Europe/London", "Europe/Berlin", "America/New_York", "America/Los_Angeles", "Australia/Sydney"];

export function SettingsPage() {
  const settings = useApp((state) => state.settings);
  const patchSettings = useApp((state) => state.patchSettings);
  const toast = useApp((state) => state.toast);
  const [tab, setTab] = React.useState<Tab>("appearance");
  const [busy, setBusy] = React.useState(false);
  const [apiKey, setApiKey] = React.useState("");
  const [keyStored, setKeyStored] = React.useState(false);
  const [keyBusy, setKeyBusy] = React.useState(false);
  const diagApi = useApi<Diagnostics>("/api/diagnostics");
  const aiApi = useApi<{ ok: boolean; provider: string | null; models: string[]; error?: string; hint?: string; external?: boolean }>("/api/ai/status");

  React.useEffect(() => {
    void hasStoredApiKey().then(setKeyStored);
  }, []);

  const restart = async () => {
    setBusy(true);
    try {
      const info = await restartEngine();
      diagApi.reload();
      toast({
        title: "Forensic engine restarted",
        description: info ? `now serving on 127.0.0.1:${info.port}` : "desktop application only",
        tone: "success",
      });
    } catch (err) {
      toast({ title: "Engine restart failed", description: (err as Error).message, tone: "error" });
    } finally {
      setBusy(false);
    }
  };

  const saveKey = async () => {
    setKeyBusy(true);
    try {
      await saveApiKey(apiKey.trim());
      setApiKey("");
      setKeyStored(true);
      // The engine reads the key from its environment, so restart to apply it.
      await restartEngine();
      diagApi.reload();
      toast({ title: "API key stored in the OS credential vault", description: "The engine was restarted with the key.", tone: "success" });
    } catch (err) {
      toast({ title: "Could not store the API key", description: (err as Error).message, tone: "error" });
    } finally {
      setKeyBusy(false);
    }
  };

  const clearKey = async () => {
    setKeyBusy(true);
    try {
      await clearApiKey();
      setKeyStored(false);
      await restartEngine();
      diagApi.reload();
      toast({ title: "API key removed", tone: "success" });
    } catch (err) {
      toast({ title: "Could not remove the API key", description: (err as Error).message, tone: "error" });
    } finally {
      setKeyBusy(false);
    }
  };

  const update = async (values: Partial<Settings>) => {
    patchSettings(values);
    setBusy(true);
    try {
      await patch("/api/settings", values);
    } catch (err) {
      toast({ title: "Could not persist setting", description: (err as Error).message, tone: "error" });
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex h-full min-h-0 flex-col">
      <PageHeader
        title="Settings & diagnostics"
        description="All preferences are stored locally. No account, telemetry or cloud synchronisation exists in this application."
        badges={busy ? <Badge tone="amber">saving…</Badge> : <Badge tone="teal">local only</Badge>}
        actions={<Tabs value={tab} onChange={setTab} tabs={[
          { value: "appearance", label: "Appearance" },
          { value: "forensic", label: "Forensic" },
          { value: "ai", label: "AI" },
          { value: "storage", label: "Storage" },
          { value: "diagnostics", label: "Diagnostics" },
        ]} />}
      />
      <div className="min-h-0 flex-1 overflow-y-auto p-4 scroll-thin">
        {!settings ? <Spinner label="Loading settings…" /> : null}
        {settings && tab === "appearance" ? (
          <div className="grid gap-3 lg:grid-cols-2">
            <Panel title="Theme & density">
              <div className="space-y-2">
                <Field label="Theme">
                  <Select value={settings.theme} onChange={(event) => void update({ theme: event.target.value as Settings["theme"] })}>
                    <option value="dark">Dark graphite</option>
                    <option value="light">Light</option>
                  </Select>
                </Field>
                <Field label="Display density">
                  <Select value={settings.density} onChange={(event) => void update({ density: event.target.value as Settings["density"] })}>
                    <option value="comfortable">Comfortable</option>
                    <option value="compact">Compact</option>
                  </Select>
                </Field>
                <Field label="Language">
                  <Select value={settings.language} onChange={(event) => void update({ language: event.target.value })}>
                    <option value="en">English</option>
                    <option value="ml">മലയാളം (content only)</option>
                    <option value="hi">हिन्दी (content only)</option>
                    <option value="ta">தமிழ் (content only)</option>
                    <option value="ar">العربية (content only)</option>
                  </Select>
                </Field>
                <p className="text-[10.5px] text-muted">
                  Interface copy is English. Evidence in any language is preserved and searchable regardless of this setting.
                </p>
              </div>
            </Panel>
            <Panel title="Workstation preferences">
              <div className="space-y-2">
                <Switch checked={settings.keyboard_shortcuts} onChange={(value) => void update({ keyboard_shortcuts: value })} label="Keyboard shortcuts" hint="Ctrl/Cmd+K global search, G then D for dashboard, / to focus search." />
                <Switch checked={settings.application_lock} onChange={(value) => void update({ application_lock: value })} label="Application lock" hint="Require the OS credential prompt when opening the application." />
                <Field label="Date format">
                  <Select value={settings.date_format} onChange={(event) => void update({ date_format: event.target.value })}>
                    <option value="locale">Follow system locale</option>
                    <option value="iso">ISO 8601 (2024-01-31)</option>
                    <option value="dmy">Day first (31/01/2024)</option>
                    <option value="mdy">Month first (01/31/2024)</option>
                  </Select>
                </Field>
              </div>
            </Panel>
          </div>
        ) : null}

        {settings && tab === "forensic" ? (
          <div className="grid gap-3 lg:grid-cols-2">
            <Panel title="Integrity & import">
              <div className="space-y-2">
                <Switch checked={settings.hash_verification} onChange={(value) => void update({ hash_verification: value })} label="Verify evidence hashes on open" hint="Re-hashes stored originals and compares with the ingestion hash." />
                <Switch checked={settings.validate_imports} onChange={(value) => void update({ validate_imports: value })} label="Validate archives before extraction" hint="Rejects path traversal, symlinks, bombs and oversized entries." />
                <Field label="Duplicate handling">
                  <Select value={settings.duplicate_handling} onChange={(event) => void update({ duplicate_handling: event.target.value })}>
                    <option value="skip">Skip records already present (recommended)</option>
                    <option value="observe">Record as another observation only</option>
                  </Select>
                </Field>
                <Field label="Source timezone default">
                  <Select value={settings.source_timezone} onChange={(event) => void update({ source_timezone: event.target.value })}>
                    {TIMEZONES.map((zone) => <option key={zone} value={zone}>{zone}</option>)}
                  </Select>
                </Field>
              </div>
            </Panel>
            <Panel title="Interpretation & anomalies">
              <div className="space-y-2">
                <Switch
                  checked={settings.interpretive_analysis}
                  onChange={(value) => void update({ interpretive_analysis: value })}
                  label="Enable interpretive analysis (sentiment, emotion words)"
                  hint="Off keeps every objective count and chart; only linguistic estimates are hidden."
                />
                <Field label="Anomaly sensitivity" hint={`${settings.anomaly_sensitivity}σ`}>
                  <input type="range" min={2} max={6} step={0.5} value={settings.anomaly_sensitivity}
                    onChange={(event) => void update({ anomaly_sensitivity: Number(event.target.value) })}
                    className="w-full accent-cyan-400" />
                </Field>
                <Field label="Audit retention (days)">
                  <Input type="number" value={Number(settings.audit_retention_days)} onChange={(event) => void update({ audit_retention_days: Number(event.target.value) })} />
                </Field>
                <Field label="Report defaults">
                  <Select value={settings.report_theme} onChange={(event) => void update({ report_theme: event.target.value })}>
                    <option value="graphite">Graphite</option>
                    <option value="light">Light</option>
                  </Select>
                </Field>
              </div>
            </Panel>
          </div>
        ) : null}

        {settings && tab === "ai" ? (
          <div className="grid gap-3 lg:grid-cols-2">
            <Panel title="Local model (Ollama)">
              <div className="space-y-2">
                <Switch checked={settings.ai_enabled} onChange={(value) => void update({ ai_enabled: value })} label="Enable AI features" hint="Objective analytics keep working when disabled." />
                <Field label="Provider">
                  <Select value={settings.ai_provider} onChange={(event) => void update({ ai_provider: event.target.value })}>
                    <option value="ollama">Ollama (local)</option>
                    <option value="openai-compatible">OpenAI-compatible endpoint</option>
                  </Select>
                </Field>
                <Field label="Model">
                  {aiApi.data && aiApi.data.models.length > 0 ? (
                    <Select value={settings.ai_model} onChange={(event) => void update({ ai_model: event.target.value })}>
                      {aiApi.data.models.map((model) => <option key={model} value={model}>{model}</option>)}
                    </Select>
                  ) : (
                    <Input value={settings.ai_model} onChange={(event) => void update({ ai_model: event.target.value })} />
                  )}
                </Field>
                <div className="grid grid-cols-2 gap-2">
                  <Field label="Context length">
                    <Input type="number" value={settings.ai_context_length} onChange={(event) => void update({ ai_context_length: Number(event.target.value) })} />
                  </Field>
                  <Field label="Temperature">
                    <Input type="number" step="0.1" min="0" max="1" value={settings.ai_temperature} onChange={(event) => void update({ ai_temperature: Number(event.target.value) })} />
                  </Field>
                </div>
                <Field label="Embedding model" hint="optional semantic retrieval">
                  <Input value={settings.ai_embedding_model} onChange={(event) => void update({ ai_embedding_model: event.target.value })} />
                </Field>
                <Field label="Transcription model">
                  <Input value={settings.transcription_model} onChange={(event) => void update({ transcription_model: event.target.value })} />
                </Field>
              </div>
            </Panel>
            <Panel title="External provider">
              <div className="space-y-2">
                <Switch
                  checked={settings.ai_external_enabled}
                  onChange={(value) => void update({ ai_external_enabled: value })}
                  label="Allow an external AI endpoint"
                  hint="When enabled, the retrieved excerpts you see in an answer are sent to that endpoint. Disabled by default."
                />
                <Field label="Base URL">
                  <Input value={settings.ai_external_base_url} placeholder="https://api.example.com/v1" onChange={(event) => void update({ ai_external_base_url: event.target.value })} />
                </Field>
                {isDesktop() ? (
                  <div className="space-y-2 rounded-lg border border-line bg-elevated/50 p-2">
                    <Field
                      label="Provider API key"
                      hint={keyStored ? "stored in the OS credential vault" : "not stored"}
                    >
                      <Input
                        type="password"
                        autoComplete="off"
                        value={apiKey}
                        placeholder={keyStored ? "•••••• stored — paste a new key to replace" : "paste the provider key"}
                        onChange={(event) => setApiKey(event.target.value)}
                      />
                    </Field>
                    <div className="flex gap-2">
                      <Button size="sm" loading={keyBusy} disabled={!apiKey.trim()} onClick={() => void saveKey()}>
                        <KeyRound className="h-3 w-3" /> Store key
                      </Button>
                      <Button size="sm" variant="ghost" loading={keyBusy} disabled={!keyStored} onClick={() => void clearKey()}>
                        Remove key
                      </Button>
                    </div>
                    <p className="text-[10px] leading-relaxed text-muted">
                      The key is written to the Windows Credential Manager through the desktop shell, never to the
                      database, a settings file or a log. The engine is restarted so it can read the key from its
                      own environment.
                    </p>
                  </div>
                ) : (
                  <div className="rounded-lg border border-amber/30 bg-amber/8 p-2 text-[10.5px] leading-relaxed text-amber">
                    In this browser preview the engine can only read a key from <span className="mono">OPENAI_API_KEY</span>.
                    Run the desktop application to store a key in the operating-system credential vault.
                  </div>
                )}
                <div className="rounded-lg border border-line bg-elevated/50 p-2 text-[10.5px] text-muted">
                  {aiApi.data?.ok ? (
                    <span className="flex items-center gap-1 text-teal"><CheckCircle2 className="h-3 w-3" /> {aiApi.data.provider} reachable · {aiApi.data.models.length} models</span>
                  ) : (
                    <span className="text-amber">{aiApi.data?.error ?? aiApi.data?.hint ?? "Provider not reachable"}</span>
                  )}
                </div>
              </div>
            </Panel>
          </div>
        ) : null}

        {settings && tab === "storage" ? (
          <div className="grid gap-3 lg:grid-cols-2">
            <Panel title="Locations">
              <div className="space-y-2">
                <Field label="Application data directory" hint="read from the engine">
                  <Input value={diagApi.data?.data_dir ?? ""} readOnly />
                </Field>
                <Field label="Database">
                  <Input value={diagApi.data?.db_path ?? ""} readOnly />
                </Field>
                <Field label="Default evidence directory">
                  <Input value={settings.default_evidence_dir} onChange={(event) => void update({ default_evidence_dir: event.target.value })} />
                </Field>
                <Field label="Default report directory">
                  <Input value={settings.default_report_dir} onChange={(event) => void update({ default_report_dir: event.target.value })} />
                </Field>
                <Switch checked={settings.auto_backup} onChange={(value) => void update({ auto_backup: value })} label="Automatic local backup" hint="Creates an encrypted case backup on the configured interval." />
                <Field label="Backup interval (hours)">
                  <Input type="number" value={Number(settings.auto_backup_interval_hours)} onChange={(event) => void update({ auto_backup_interval_hours: Number(event.target.value) })} />
                </Field>
              </div>
            </Panel>
            <Panel title="Storage usage">
              {diagApi.data ? (
                <div className="space-y-2 text-[11.5px]">
                  <Row label="Database size" value={bytes(diagApi.data.db_bytes)} />
                  <Row label="Free disk" value={bytes(diagApi.data.disk_free_bytes)} />
                  <Row label="Total disk" value={bytes(diagApi.data.disk_total_bytes)} />
                  <Row label="Cases" value={num(diagApi.data.cases)} />
                  <Row label="Messages" value={num(diagApi.data.messages)} />
                  <Row label="Audit entries" value={num(diagApi.data.audit_entries)} />
                  <p className="pt-2 text-[10.5px] leading-relaxed text-muted">
                    Case folders contain originals, derived files, thumbnails, transcripts, analysis output,
                    reports and exports. Application binaries live separately, so uninstalling never removes
                    your cases.
                  </p>
                </div>
              ) : (
                <Spinner />
              )}
            </Panel>
          </div>
        ) : null}

        {settings && tab === "diagnostics" ? (
          <div className="grid gap-3 lg:grid-cols-2">
            <Panel
              title="Engine"
              actions={
                <div className="flex gap-1">
                  <Button size="sm" variant="ghost" disabled={!isDesktop() || busy} onClick={() => void restart()}>
                    <RotateCw className="h-3 w-3" /> Restart
                  </Button>
                  <Button size="sm" variant="ghost" onClick={diagApi.reload}>Refresh</Button>
                </div>
              }
            >
              {diagApi.loading ? <Spinner /> : null}
              {diagApi.error ? <ErrorState error={diagApi.error} onRetry={diagApi.reload} /> : null}
              {diagApi.data ? (
                <div className="space-y-1.5 text-[11.5px]">
                  <Row label="Engine version" value={diagApi.data.engine_version} />
                  <Row label="Python" value={diagApi.data.python} />
                  <Row label="SQLite" value={diagApi.data.sqlite} />
                  <Row label="FTS5" value={diagApi.data.fts5 ? "available" : "missing"} />
                  <Row label="Platform" value={diagApi.data.platform} />
                </div>
              ) : null}
            </Panel>
            <Panel title="Capabilities">
              {diagApi.data ? (
                <div className="space-y-2 text-[11.5px]">
                  <div className="flex items-center gap-2">
                    <Cpu className="h-3.5 w-3.5 text-accent" />
                    <span className="text-muted">Local AI</span>
                    <Badge tone={diagApi.data.ai.ok ? "teal" : "amber"}>{diagApi.data.ai.ok ? "ready" : "not running"}</Badge>
                  </div>
                  <div className="flex items-center gap-2">
                    <Sparkles className="h-3.5 w-3.5 text-accent" />
                    <span className="text-muted">Transcription</span>
                    <Badge tone={diagApi.data.transcription.available ? "teal" : "amber"}>{diagApi.data.transcription.available ? "ready" : "no model"}</Badge>
                  </div>
                  <div className="flex items-center gap-2">
                    <HardDrive className="h-3.5 w-3.5 text-accent" />
                    <span className="text-muted">Media tools</span>
                    <span className="text-ink">
                      {[diagApi.data.media_tools.ffprobe ? "ffprobe" : null, diagApi.data.media_tools.exiftool ? "exiftool" : null, diagApi.data.media_tools.pillow ? "Pillow" : null].filter(Boolean).join(", ") || "python fallbacks"}
                    </span>
                  </div>
                  <div className="flex items-center gap-2">
                    <Database className="h-3.5 w-3.5 text-accent" />
                    <span className="text-muted">Offline operation</span>
                    <Badge tone="teal">yes</Badge>
                  </div>
                  <p className="pt-1 text-[10.5px] text-muted">{diagApi.data.transcription.hint}</p>
                </div>
              ) : null}
            </Panel>
            <Panel title="Privacy posture" className="lg:col-span-2">
              <div className="grid gap-2 sm:grid-cols-2">
                {[
                  ["No accounts", "The application never asks you to sign in."],
                  ["No telemetry", "No analytics or crash reporting SDK is bundled."],
                  ["No sync", "Nothing is uploaded automatically; external AI is opt-in."],
                  ["Local evidence", "Originals, thumbnails and reports live in the case directory."],
                  ["Least privilege", "The Tauri shell exposes only the commands the UI uses."],
                  ["Audit trail", "Imports, exports, reports and analysis runs are logged."],
                ].map(([title, body]) => (
                  <div key={title} className="flex items-start gap-2 rounded-lg border border-line bg-elevated/50 p-2">
                    <ShieldCheck className="mt-0.5 h-3.5 w-3.5 shrink-0 text-teal" />
                    <div>
                      <p className="text-[11.5px] text-ink">{title}</p>
                      <p className="text-[10.5px] text-muted">{body}</p>
                    </div>
                  </div>
                ))}
              </div>
            </Panel>
          </div>
        ) : null}

        {settings ? (
          <div className="mt-3 flex justify-end">
            <Button
              variant="ghost"
              onClick={async () => {
                const fresh = await get<Settings>("/api/settings");
                useApp.getState().setSettings(fresh);
                toast({ title: "Settings reloaded from the engine", tone: "info" });
              }}
            >
              Reload settings
            </Button>
          </div>
        ) : null}
        {!settings ? <EmptyState title="Settings unavailable" /> : null}
      </div>
    </div>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between gap-2 border-b border-line/50 pb-1.5 last:border-0">
      <span className="text-muted">{label}</span>
      <span className="truncate text-ink" title={value}>{value}</span>
    </div>
  );
}
