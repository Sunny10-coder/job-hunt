import { AlertTriangle, Play, ShieldAlert } from "lucide-react";
import * as React from "react";
import { MessageInspector } from "@/components/MessageInspector";
import { PageHeader } from "@/components/layout/PageHeader";
import { Badge, Button, EmptyState, ErrorState, Kpi, Panel, Spinner, Tabs } from "@/components/ui/primitives";
import { post } from "@/lib/api";
import { useApi } from "@/hooks/useApi";
import { useCase } from "@/hooks/useCaseContext";
import { dateTime, num } from "@/lib/format";
import { useApp } from "@/stores/app";

interface RecoveryResponse {
  findings: { id: string; kind: string; status: string; summary: string; detail: Record<string, unknown>; message_id: string | null; created_at: string }[];
  classifications: Record<string, string>;
  counts: Record<string, number>;
  comparisons: { evidence_a: { original_name: string }; evidence_b: { original_name: string }; shared: number; shared_conversations: number; excluded_conversations: Record<string, number>; method: string }[];
  limitations?: string[];
}

const TONE: Record<string, "danger" | "amber" | "teal" | "muted"> = {
  deletion_indicator: "danger",
  missing_attachment: "amber",
  present_in_earlier_snapshot: "teal",
  unverified_discrepancy: "amber",
  recovered_from_evidence: "teal",
  not_recoverable: "muted",
};

export function RecoveryPage() {
  const { caseId } = useCase();
  const toast = useApp((state) => state.toast);
  const [busy, setBusy] = React.useState(false);
  const [filter, setFilter] = React.useState<string>("all");
  const [inspect, setInspect] = React.useState<string | null>(null);

  const api = useApi<RecoveryResponse>(caseId ? `/api/cases/${caseId}/recovery` : null, [caseId]);

  const analyze = async () => {
    setBusy(true);
    try {
      await post(`/api/cases/${caseId}/recovery/analyze`);
      api.reload();
      toast({ title: "Recovery analysis complete", tone: "success" });
    } catch (err) {
      toast({ title: "Analysis failed", description: (err as Error).message, tone: "error" });
    } finally {
      setBusy(false);
    }
  };

  const findings = (api.data?.findings ?? []).filter((finding) => filter === "all" || finding.status === filter);
  const counts = React.useMemo(() => {
    const map: Record<string, number> = {};
    for (const finding of api.data?.findings ?? []) map[finding.status] = (map[finding.status] ?? 0) + 1;
    return map;
  }, [api.data]);

  return (
    <div className="flex h-full min-h-0 flex-col">
      <PageHeader
        title="Message recovery analysis"
        description="Reports only what the surviving evidence supports: deletion indicators, missing attachments and cross-snapshot differences. Deleted text is never reconstructed."
        badges={<Badge tone="amber"><ShieldAlert className="h-3 w-3" /> indicators only</Badge>}
        actions={
          <Button variant="primary" loading={busy} onClick={() => void analyze()}>
            <Play className="h-3.5 w-3.5" /> Run analysis
          </Button>
        }
      />
      <div className="min-h-0 flex-1 overflow-y-auto p-4 scroll-thin">
        {api.loading && !api.data ? <Spinner label="Loading findings…" /> : null}
        {api.error ? <ErrorState error={api.error} onRetry={api.reload} /> : null}
        {api.data ? (
          <div className="space-y-3">
            <div className="grid grid-cols-2 gap-2 md:grid-cols-3 xl:grid-cols-6">
              <Kpi label="Deletion indicators" value={num(counts.deletion_indicator)} tone="danger" />
              <Kpi label="Missing attachments" value={num(counts.missing_attachment)} tone="amber" />
              <Kpi label="In earlier snapshot" value={num(counts.present_in_earlier_snapshot)} tone="teal" />
              <Kpi label="Unverified" value={num(counts.unverified_discrepancy)} />
              <Kpi label="Total findings" value={num(api.data.findings.length)} />
              <Kpi label="Snapshots compared" value={num(api.data.comparisons.length)} />
            </div>

            <Panel
              title="Findings"
              actions={<Tabs value={filter} onChange={setFilter} tabs={[{ value: "all", label: "All", count: api.data.findings.length }, ...Object.entries(api.data.classifications).map(([value, label]) => ({ value, label, count: counts[value] ?? 0 }))]} />}
              dense
            >
              <div className="divide-y divide-line/60">
                {findings.slice(0, 300).map((finding) => (
                  <div key={finding.id} className="flex items-start gap-2 px-3 py-2">
                    <Badge tone={TONE[finding.status] ?? "muted"}>{api.data?.classifications[finding.status] ?? finding.status}</Badge>
                    <div className="min-w-0 flex-1">
                      <p className="text-[12px] text-ink">{finding.summary}</p>
                      {typeof finding.detail.note === "string" ? (
                        <p className="mt-0.5 text-[10.5px] leading-snug text-muted">{finding.detail.note}</p>
                      ) : null}
                      <p className="text-[10px] text-muted/80">{dateTime(finding.created_at)}</p>
                    </div>
                    {finding.message_id ? (
                      <Button size="sm" variant="ghost" onClick={() => setInspect(finding.message_id)}>
                        view record
                      </Button>
                    ) : null}
                  </div>
                ))}
                {findings.length === 0 ? (
                  <EmptyState
                    icon={<ShieldAlert className="h-7 w-7" />}
                    title="No findings in this classification"
                    description="Run the analysis after importing at least one export. Absence of findings is not proof that nothing was deleted."
                  />
                ) : null}
              </div>
            </Panel>

            {api.data.comparisons.length > 0 ? (
              <Panel title="Snapshot comparison" subtitle="normalised message sets per evidence item">
                <div className="space-y-2">
                  {api.data.comparisons.map((comparison, index) => (
                    <div key={index} className="rounded-lg border border-line bg-elevated/40 px-3 py-2">
                      <p className="text-[12px] text-ink">
                        {comparison.evidence_a.original_name} ↔ {comparison.evidence_b.original_name}
                      </p>
                      <p className="text-[10.5px] text-muted">
                        {num(comparison.shared)} shared records across {comparison.shared_conversations} shared conversation(s)
                      </p>
                      <p className="mt-0.5 text-[10.5px] text-muted">{comparison.method}</p>
                    </div>
                  ))}
                </div>
              </Panel>
            ) : null}

            <Panel title="Limitations">
              <ul className="space-y-1 text-[11.5px] leading-relaxed text-muted">
                <li className="flex items-start gap-1.5">
                  <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-amber" />
                  Crypt12/14/15 databases and iPhone backups are out of scope: nothing is decrypted or acquired from a device.
                </li>
                <li>Deleted message text is never reconstructed. AI may produce a clearly labelled hypothesis, kept separate from findings.</li>
                <li>A message missing from a later export may simply be outside that export's date range or excluded by export settings.</li>
                <li>Media placeholders mean the export referenced a file that was not included; this is not evidence the media never existed.</li>
              </ul>
            </Panel>
          </div>
        ) : null}
      </div>

      <MessageInspector caseId={caseId} messageId={inspect} open={Boolean(inspect)} onClose={() => setInspect(null)} />
    </div>
  );
}
