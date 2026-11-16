import { Network as NetworkIcon } from "lucide-react";
import * as React from "react";
import { NetworkGraph } from "@/components/charts/NetworkGraph";
import { PageHeader } from "@/components/layout/PageHeader";
import { Badge, Button, Checkbox, EmptyState, ErrorState, Field, Panel, Spinner } from "@/components/ui/primitives";
import { useApi } from "@/hooks/useApi";
import { useCase } from "@/hooks/useCaseContext";
import { num } from "@/lib/format";
import type { NetworkGraphData } from "@/types";

export function NetworkPage() {
  const { caseId } = useCase();
  const [includeTopics, setIncludeTopics] = React.useState(true);
  const [minMessages, setMinMessages] = React.useState(1);
  const [from, setFrom] = React.useState("");
  const [to, setTo] = React.useState("");
  const [selected, setSelected] = React.useState<NetworkGraphData["nodes"][number] | null>(null);

  const query = new URLSearchParams();
  query.set("topics", includeTopics ? "1" : "0");
  query.set("min_messages", String(minMessages));
  if (from) query.set("from", from);
  if (to) query.set("to", to);

  const graphApi = useApi<NetworkGraphData>(caseId ? `/api/cases/${caseId}/network?${query.toString()}` : null, [caseId, includeTopics, minMessages, from, to]);

  const connected = React.useMemo(() => {
    if (!graphApi.data || !selected) return [];
    return graphApi.data.edges
      .filter((edge) => edge.source === selected.id || edge.target === selected.id)
      .map((edge) => {
        const otherId = edge.source === selected.id ? edge.target : edge.source;
        const other = graphApi.data?.nodes.find((node) => node.id === otherId);
        return { ...edge, other };
      });
  }, [graphApi.data, selected]);

  return (
    <div className="flex h-full min-h-0 flex-col">
      <PageHeader
        title="Relationship network"
        description="Contacts, groups and topics observed in the evidence. Solid edges are observed relationships; dashed edges are inferred topic associations only."
        badges={
          graphApi.data ? (
            <>
              <Badge tone="accent">{String(graphApi.data.metrics.nodes)} nodes</Badge>
              <Badge tone="teal">{String(graphApi.data.metrics.edges)} edges</Badge>
            </>
          ) : null
        }
        actions={
          <Button variant="ghost" size="sm" onClick={graphApi.reload}>
            Refresh
          </Button>
        }
      />

      <div className="flex min-h-0 flex-1">
        <div className="min-h-0 flex-1 p-3">
          <Panel className="h-full" bodyClassName="p-1" title="Graph" subtitle={graphApi.data ? String(graphApi.data.metrics.method) : undefined}>
            {graphApi.loading && !graphApi.data ? <Spinner label="Building graph…" /> : null}
            {graphApi.error ? <ErrorState error={graphApi.error} onRetry={graphApi.reload} /> : null}
            {graphApi.data ? (
              <div className="h-full">
                <NetworkGraph data={graphApi.data} onSelect={setSelected} height={560} />
              </div>
            ) : null}
          </Panel>
        </div>

        <aside className="w-[300px] shrink-0 space-y-3 overflow-y-auto border-l border-line bg-panel/40 p-3 scroll-thin">
          <Panel title="Filters">
            <div className="space-y-2">
              <Checkbox checked={includeTopics} onChange={setIncludeTopics} label="Include topic nodes" hint="Inferred associations, drawn dashed." />
              <Field label="Minimum messages" hint={`${minMessages}`}>
                <input
                  type="range"
                  min={1}
                  max={50}
                  value={minMessages}
                  onChange={(event) => setMinMessages(Number(event.target.value))}
                  className="w-full accent-cyan-400"
                />
              </Field>
              <Field label="From">
                <input type="date" value={from} onChange={(event) => setFrom(event.target.value)} className="field text-[12px]" />
              </Field>
              <Field label="To">
                <input type="date" value={to} onChange={(event) => setTo(event.target.value)} className="field text-[12px]" />
              </Field>
            </div>
          </Panel>

          <Panel title="Network metrics" dense>
            <div className="space-y-1 p-2 text-[11.5px]">
              {graphApi.data
                ? Object.entries(graphApi.data.metrics)
                    .filter(([key]) => key !== "method")
                    .map(([key, value]) => (
                      <div key={key} className="flex items-center justify-between border-b border-line/50 py-1 last:border-0">
                        <span className="text-muted">{key}</span>
                        <span className="text-ink">{String(value)}</span>
                      </div>
                    ))
                : null}
            </div>
          </Panel>

          <Panel title="Selection" dense>
            {selected ? (
              <div className="space-y-2 p-2">
                <div>
                  <p className="text-[12.5px] font-medium text-ink">{selected.label}</p>
                  <Badge tone={selected.kind === "topic" ? "teal" : "accent"}>{selected.kind}</Badge>
                </div>
                <p className="text-[11px] text-muted">weight {num(selected.weight)}</p>
                <div className="space-y-1">
                  {connected.slice(0, 12).map((edge) => (
                    <div key={edge.id} className="rounded border border-line bg-elevated/50 px-2 py-1">
                      <p className="text-[11px] text-ink">
                        {edge.other?.label ?? "unknown"}{" "}
                        <span className="text-muted">({edge.kind})</span>
                      </p>
                      <p className="text-[10px] text-muted">
                        {edge.label} {edge.inferred ? "· inferred" : ""}
                      </p>
                    </div>
                  ))}
                </div>
              </div>
            ) : (
              <EmptyState icon={<NetworkIcon className="h-6 w-6" />} title="Click a node" description="Select any node to inspect its observed relationships." />
            )}
          </Panel>
        </aside>
      </div>
    </div>
  );
}
