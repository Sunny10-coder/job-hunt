import { Download, FileText, Play, Printer } from "lucide-react";
import * as React from "react";
import { PageHeader } from "@/components/layout/PageHeader";
import { Badge, Button, Checkbox, EmptyState, Field, Input, Panel, Select, Spinner } from "@/components/ui/primitives";
import { apiUrl, post } from "@/lib/api";
import { dateTime, num } from "@/lib/format";
import { useApi } from "@/hooks/useApi";
import { useCase } from "@/hooks/useCaseContext";
import { useApp } from "@/stores/app";
import type { Conversation } from "@/types";

const TYPES = [
  { value: "case", label: "Complete case report" },
  { value: "conversation", label: "Conversation analysis" },
  { value: "contact", label: "Contact intelligence" },
  { value: "group", label: "Group activity" },
  { value: "timeline", label: "Communication timeline" },
  { value: "media", label: "Media evidence" },
  { value: "recovery", label: "Recovery analysis" },
  { value: "ai", label: "AI-assisted analytical" },
  { value: "search", label: "Search results" },
  { value: "custom", label: "Custom investigation" },
];

const SECTIONS = [
  "summary", "metrics", "activity", "response", "topics", "contacts", "conversations",
  "participants", "events", "timeline", "media", "missing", "findings", "ai", "messages",
  "evidence", "methodology",
];

const FORMATS = [
  { value: "pdf", label: "PDF" },
  { value: "html", label: "HTML" },
  { value: "xlsx", label: "XLSX" },
  { value: "csv", label: "CSV" },
  { value: "json", label: "JSON" },
];

export function ReportsPage() {
  const { caseId } = useCase();
  const toast = useApp((state) => state.toast);
  const [type, setType] = React.useState("case");
  const [format, setFormat] = React.useState("pdf");
  const [sections, setSections] = React.useState<string[]>(["summary", "metrics", "activity", "contacts", "evidence", "methodology"]);
  const [conversationId, setConversationId] = React.useState("");
  const [from, setFrom] = React.useState("");
  const [to, setTo] = React.useState("");
  const [includeMessages, setIncludeMessages] = React.useState(true);
  const [messageLimit, setMessageLimit] = React.useState(300);
  const [theme, setTheme] = React.useState("graphite");
  const [preview, setPreview] = React.useState<string | null>(null);
  const [busy, setBusy] = React.useState(false);

  const reportsApi = useApi<{ id: string; type: string; format: string; path: string; size_bytes: number; sha256: string; created_at: string }[]>(
    caseId ? `/api/cases/${caseId}/reports` : null,
    [caseId],
  );
  const conversationsApi = useApi<Conversation[]>(caseId ? `/api/cases/${caseId}/conversations` : null, [caseId]);

  const options = () => ({
    sections,
    conversation_id: conversationId || undefined,
    date_from: from || undefined,
    date_to: to || undefined,
    include_messages: includeMessages,
    message_limit: messageLimit,
    theme,
  });

  const buildPreview = async () => {
    setBusy(true);
    try {
      const result = await post<{ html: string }>(`/api/cases/${caseId}/reports/preview`, { type, ...options() });
      setPreview(result.html);
    } catch (err) {
      toast({ title: "Preview failed", description: (err as Error).message, tone: "error" });
    } finally {
      setBusy(false);
    }
  };

  const generate = async () => {
    setBusy(true);
    try {
      const result = await post<{ path: string; sha256: string; format: string }>(`/api/cases/${caseId}/reports`, {
        type,
        format,
        options: options(),
      });
      reportsApi.reload();
      toast({ title: `${format.toUpperCase()} report generated`, description: result.sha256.slice(0, 24), tone: "success" });
    } catch (err) {
      toast({ title: "Report failed", description: (err as Error).message, tone: "error" });
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex h-full min-h-0 flex-col">
      <PageHeader
        title="Report builder"
        description="Professional PDF, HTML, XLSX, CSV or JSON reports from the current case and scope. Every report records its generation time and the SHA-256 of its evidence sources."
        badges={<Badge tone="amber">analytical work product</Badge>}
        actions={
          <>
            <Button variant="ghost" loading={busy} onClick={() => void buildPreview()}>
              <Printer className="h-3.5 w-3.5" /> Preview
            </Button>
            <Button variant="primary" loading={busy} onClick={() => void generate()}>
              <Play className="h-3.5 w-3.5" /> Generate {format.toUpperCase()}
            </Button>
          </>
        }
      />
      <div className="grid min-h-0 flex-1 grid-cols-[330px_minmax(0,1fr)]">
        <aside className="min-h-0 space-y-3 overflow-y-auto border-r border-line bg-panel/40 p-3 scroll-thin">
          <Panel title="Report">
            <div className="space-y-2">
              <Field label="Template">
                <Select value={type} onChange={(event) => setType(event.target.value)}>
                  {TYPES.map((item) => (
                    <option key={item.value} value={item.value}>{item.label}</option>
                  ))}
                </Select>
              </Field>
              <Field label="Format">
                <Select value={format} onChange={(event) => setFormat(event.target.value)}>
                  {FORMATS.map((item) => (
                    <option key={item.value} value={item.value}>{item.label}</option>
                  ))}
                </Select>
              </Field>
              <Field label="Theme">
                <Select value={theme} onChange={(event) => setTheme(event.target.value)}>
                  <option value="graphite">Graphite (dark)</option>
                  <option value="light">Light (print friendly)</option>
                </Select>
              </Field>
            </div>
          </Panel>

          <Panel title="Scope">
            <div className="space-y-2">
              <Field label="Conversation">
                <Select value={conversationId} onChange={(event) => setConversationId(event.target.value)}>
                  <option value="">Whole case</option>
                  {(conversationsApi.data ?? []).map((conversation) => (
                    <option key={conversation.id} value={conversation.id}>{conversation.title}</option>
                  ))}
                </Select>
              </Field>
              <Field label="From">
                <input type="date" value={from} onChange={(event) => setFrom(event.target.value)} className="field text-[12px]" />
              </Field>
              <Field label="To">
                <input type="date" value={to} onChange={(event) => setTo(event.target.value)} className="field text-[12px]" />
              </Field>
              <Field label="Verbatim message cap">
                <Input type="number" value={messageLimit} min={0} max={5000} onChange={(event) => setMessageLimit(Number(event.target.value))} />
              </Field>
              <Checkbox checked={includeMessages} onChange={setIncludeMessages} label="Include verbatim message records" />
            </div>
          </Panel>

          <Panel title="Sections">
            <div className="grid grid-cols-2 gap-1.5">
              {SECTIONS.map((section) => (
                <Checkbox
                  key={section}
                  checked={sections.includes(section)}
                  onChange={(value) => setSections((current) => (value ? [...current, section] : current.filter((item) => item !== section)))}
                  label={<span className="text-[11px] capitalize">{section}</span>}
                />
              ))}
            </div>
          </Panel>

          <Panel title="Generated reports" dense>
            <div className="divide-y divide-line/60">
              {(reportsApi.data ?? []).map((report) => (
                <div key={report.id} className="flex items-center justify-between gap-2 px-3 py-2">
                  <div className="min-w-0">
                    <p className="truncate text-[11.5px] text-ink">
                      {report.type} · {report.format.toUpperCase()}
                    </p>
                    <p className="text-[10px] text-muted">{dateTime(report.created_at)} · {num(report.size_bytes)} B</p>
                  </div>
                  <Button size="icon" variant="ghost" onClick={() => window.open(apiUrl(`/api/reports/${report.id}/download`), "_blank")}>
                    <Download className="h-3.5 w-3.5" />
                  </Button>
                </div>
              ))}
              {(reportsApi.data ?? []).length === 0 ? <p className="p-3 text-[11px] text-muted">No reports generated yet.</p> : null}
            </div>
          </Panel>
        </aside>

        <div className="min-h-0 overflow-hidden p-3">
          {preview ? (
            <div className="surface h-full overflow-hidden">
              <iframe title="Report preview" srcDoc={preview} className="h-full w-full border-0 bg-white" />
            </div>
          ) : (
            <Panel className="h-full">
              {busy ? (
                <Spinner label="Rendering preview…" />
              ) : (
                <EmptyState
                  icon={<FileText className="h-8 w-8" />}
                  title="No preview yet"
                  description="Choose a template and scope, then preview the exact document that will be exported. Reports always include the evidence hashes and a non-certification disclaimer."
                />
              )}
            </Panel>
          )}
        </div>
      </div>
    </div>
  );
}
