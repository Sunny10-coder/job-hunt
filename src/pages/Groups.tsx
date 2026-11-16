import { PageHeader } from "@/components/layout/PageHeader";
import * as React from "react";
import { useSearchParams } from "react-router-dom";
import { Chart } from "@/components/charts/Chart";
import { Badge, EmptyState, ErrorState, Panel, Spinner } from "@/components/ui/primitives";
import { barOption, lineOption, pieOption } from "@/lib/charts";
import { dateTime, num } from "@/lib/format";
import { useApi } from "@/hooks/useApi";
import { useCase } from "@/hooks/useCaseContext";
import type { Conversation } from "@/types";

interface GroupAnalysis {
  conversation: Conversation;
  participants: { contact_id: string; name: string; messages: number; media: number; avg_length: number; share: number; first_at: string; last_at: string }[];
  participation_balance: { gini: number; top_share: number; formula: string };
  events: { id: string; event_type: string; actor: string | null; target: string | null; occurred_at: string; raw_text: string }[];
  monthly: { bucket: string; count: number }[];
  media_files: number;
  words: { word: string; count: number }[];
  response: { samples: number; median_minutes: number | null; excluded_session_breaks: number; methodology: Record<string, string | number> };
  note: string;
}

export function GroupsPage() {
  const { caseId } = useCase();
  const [params, setParams] = useSearchParams();
  const selected = params.get("group");

  const groupsApi = useApi<Conversation[]>(caseId ? `/api/cases/${caseId}/groups` : null, [caseId]);
  const groups = groupsApi.data ?? [];

  React.useEffect(() => {
    if (!selected && groups.length > 0) {
      const next = new URLSearchParams(params);
      next.set("group", groups[0].id);
      setParams(next, { replace: true });
    }
  }, [groups, selected, params, setParams]);

  const analysisApi = useApi<GroupAnalysis>(caseId && selected ? `/api/cases/${caseId}/groups/${selected}` : null, [caseId, selected]);

  return (
    <div className="flex h-full min-h-0 flex-col">
      <PageHeader
        title="Group intelligence"
        description="Participant contribution, activity and recorded membership events. Membership is never inferred from silence or missing evidence."
        badges={<Badge tone="teal">{num(groups.length)} groups</Badge>}
      />
      <div className="grid min-h-0 flex-1 grid-cols-[270px_minmax(0,1fr)]">
        <aside className="min-h-0 overflow-y-auto border-r border-line bg-panel/40 scroll-thin">
          {groupsApi.loading ? <Spinner /> : null}
          {groups.map((group) => (
            <button
              key={group.id}
              onClick={() => {
                const next = new URLSearchParams(params);
                next.set("group", group.id);
                setParams(next);
              }}
              className={`w-full border-b border-line/50 px-3 py-2 text-left hover:bg-elevated/60 ${selected === group.id ? "bg-elevated" : ""}`}
            >
              <p className="truncate text-[12.5px] text-ink">{group.title}</p>
              <p className="text-[10.5px] text-muted">
                {num(group.message_count)} messages · {num(group.participants ?? 0)} participants
              </p>
            </button>
          ))}
          {groups.length === 0 && !groupsApi.loading ? (
            <EmptyState title="No group chats" description="Group analytics appear when an imported export contains a group conversation." />
          ) : null}
        </aside>

        <div className="min-h-0 overflow-y-auto p-4 scroll-thin">
          {analysisApi.loading ? <Spinner label="Analysing group…" /> : null}
          {analysisApi.error ? <ErrorState error={analysisApi.error} onRetry={analysisApi.reload} /> : null}
          {analysisApi.data ? (
            <div className="space-y-3">
              <div className="grid grid-cols-2 gap-2 md:grid-cols-4">
                <Metric label="Messages" value={num(analysisApi.data.conversation.message_count)} />
                <Metric label="Participants" value={num(analysisApi.data.participants.length)} />
                <Metric label="Media files" value={num(analysisApi.data.media_files)} />
                <Metric label="Participation Gini" value={analysisApi.data.participation_balance.gini.toFixed(3)} />
              </div>

              <div className="grid gap-3 lg:grid-cols-2">
                <Panel title="Participation share" subtitle="share of messages per participant">
                  <Chart option={pieOption(analysisApi.data.participants.map((p) => ({ name: p.name, value: p.messages })))} height={250} />
                </Panel>
                <Panel title="Messages per month">
                  <Chart option={lineOption(analysisApi.data.monthly.map((row) => row.bucket), analysisApi.data.monthly.map((row) => row.count))} height={250} />
                </Panel>
              </div>

              <Panel title="Participant ranking" dense>
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Participant</th>
                      <th>Messages</th>
                      <th>Share</th>
                      <th>Media</th>
                      <th>Avg length</th>
                      <th>First</th>
                      <th>Last</th>
                    </tr>
                  </thead>
                  <tbody>
                    {analysisApi.data.participants.map((participant) => (
                      <tr key={participant.contact_id}>
                        <td className="text-ink">{participant.name}</td>
                        <td>{num(participant.messages)}</td>
                        <td>{participant.share.toFixed(1)}%</td>
                        <td>{num(participant.media)}</td>
                        <td>{participant.avg_length}</td>
                        <td className="text-[10.5px] text-muted">{dateTime(participant.first_at)}</td>
                        <td className="text-[10.5px] text-muted">{dateTime(participant.last_at)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </Panel>

              <div className="grid gap-3 lg:grid-cols-2">
                <Panel title="Recorded membership events" dense>
                  <div className="divide-y divide-line/60">
                    {analysisApi.data.events.map((event) => (
                      <div key={event.id} className="px-3 py-2">
                        <div className="flex items-center justify-between gap-2">
                          <span className="text-[12px] text-ink">{event.event_type.replace(/_/g, " ")}</span>
                          <span className="text-[10.5px] text-muted">{dateTime(event.occurred_at)}</span>
                        </div>
                        <p className="text-[10.5px] text-muted">{event.raw_text}</p>
                      </div>
                    ))}
                    {analysisApi.data.events.length === 0 ? (
                      <EmptyState title="No events recorded" description="The export contains no membership or admin notices." />
                    ) : null}
                  </div>
                </Panel>

                <Panel title="Frequent terms" dense>
                  <div className="p-2">
                    <Chart option={barOption(analysisApi.data.words.slice(0, 12).map((w) => w.word), analysisApi.data.words.slice(0, 12).map((w) => w.count), { horizontal: true })} height={260} />
                  </div>
                </Panel>
              </div>

              <Panel title="Response behaviour (group)">
                <p className="text-[11.5px] leading-relaxed text-muted">
                  {analysisApi.data.response.samples} response pairs · median{" "}
                  {analysisApi.data.response.median_minutes ?? "—"} minutes ·{" "}
                  {analysisApi.data.response.excluded_session_breaks} session breaks excluded.
                  In a group a single "response" is ambiguous, so these numbers are reported with
                  that caveat rather than as a reply-latency measure.
                </p>
                <p className="mt-2 text-[11px] text-muted">{analysisApi.data.note}</p>
              </Panel>
            </div>
          ) : null}
        </div>
      </div>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="surface px-3 py-2">
      <p className="kpi-label">{label}</p>
      <p className="mt-0.5 text-[15px] font-semibold text-ink">{value}</p>
    </div>
  );
}
