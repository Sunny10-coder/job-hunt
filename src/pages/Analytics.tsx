import { Activity, Brain, Timer } from "lucide-react";
import * as React from "react";
import { Chart } from "@/components/charts/Chart";
import { PageHeader } from "@/components/layout/PageHeader";
import { Badge, Button, EmptyState, ErrorState, Field, Kpi, Panel, Select, Spinner, Tabs } from "@/components/ui/primitives";
import { useApi } from "@/hooks/useApi";
import { useCase } from "@/hooks/useCaseContext";
import { barOption, heatmapOption, lineOption } from "@/lib/charts";
import { dateTime, num, pct } from "@/lib/format";
import type { AnalyticsBundle, Conversation } from "@/types";

type Tab = "activity" | "response" | "language";

interface SentimentResult {
  disabled?: boolean;
  message?: string;
  scanned_messages?: number;
  counts?: Record<string, number>;
  share?: Record<string, number>;
  series?: { date: string; positive: number; negative: number; neutral: number; score: number }[];
  emotions?: { emotion: string; count: number; examples: string[] }[];
  by_conversation?: { conversation: string; positive: number; negative: number; neutral: number }[];
  method?: string;
  disclaimer?: string;
}

export function AnalyticsPage() {
  const { caseId } = useCase();
  const [tab, setTab] = React.useState<Tab>("activity");
  const [conversationId, setConversationId] = React.useState("");
  const [from, setFrom] = React.useState("");
  const [to, setTo] = React.useState("");

  const conversationsApi = useApi<Conversation[]>(caseId ? `/api/cases/${caseId}/conversations` : null, [caseId]);
  const query = new URLSearchParams();
  if (conversationId) query.set("conversation_id", conversationId);
  if (from) query.set("from", from);
  if (to) query.set("to", to);
  const suffix = query.toString() ? `?${query.toString()}` : "";

  const analyticsApi = useApi<AnalyticsBundle>(caseId ? `/api/cases/${caseId}/analytics${suffix}` : null, [caseId, conversationId, from, to]);
  const sentimentApi = useApi<SentimentResult>(
    caseId && tab === "language" ? `/api/cases/${caseId}/sentiment${conversationId ? `?conversation_id=${conversationId}` : ""}` : null,
    [caseId, conversationId, tab],
  );

  const data = analyticsApi.data;

  return (
    <div className="flex h-full min-h-0 flex-col">
      <PageHeader
        title="Communication analytics"
        description="Deterministic aggregates over imported records. Every panel states its formula and the underlying model (UTC buckets, session gaps, deduplicated messages)."
        actions={
          <Tabs
            value={tab}
            onChange={setTab}
            tabs={[
              { value: "activity", label: "Activity" },
              { value: "response", label: "Response" },
              { value: "language", label: "Language & sentiment" },
            ]}
          />
        }
        badges={data ? <Badge tone="accent">{num(data.overview.real_messages)} messages</Badge> : null}
      />

      <div className="flex flex-wrap items-end gap-2 border-b border-line bg-panel/50 px-4 py-2">
        <Field label="Conversation" className="w-64">
          <Select value={conversationId} onChange={(event) => setConversationId(event.target.value)}>
            <option value="">All conversations</option>
            {(conversationsApi.data ?? []).map((conversation) => (
              <option key={conversation.id} value={conversation.id}>
                {conversation.title}
              </option>
            ))}
          </Select>
        </Field>
        <Field label="From" className="w-40">
          <input type="date" value={from} onChange={(event) => setFrom(event.target.value)} className="field text-[12px]" />
        </Field>
        <Field label="To" className="w-40">
          <input type="date" value={to} onChange={(event) => setTo(event.target.value)} className="field text-[12px]" />
        </Field>
        <Button variant="ghost" size="sm" onClick={() => { setFrom(""); setTo(""); setConversationId(""); }}>
          Reset filters
        </Button>
        <span className="ml-auto text-[10.5px] text-muted">
          {data ? `${dateTime(data.overview.first_at)} → ${dateTime(data.overview.last_at)}` : ""}
        </span>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto p-4 scroll-thin">
        {analyticsApi.loading && !data ? <Spinner label="Aggregating…" /> : null}
        {analyticsApi.error ? <ErrorState error={analyticsApi.error} onRetry={analyticsApi.reload} /> : null}
        {data ? (
          tab === "activity" ? (
            <div className="space-y-3">
              <div className="grid grid-cols-2 gap-2 md:grid-cols-3 xl:grid-cols-6">
                <Kpi label="Messages" value={num(data.overview.real_messages)} tone="accent" />
                <Kpi label="Active days" value={num(data.overview.active_days)} />
                <Kpi label="Avg / day" value={data.overview.avg_messages_per_active_day} />
                <Kpi label="Avg length" value={`${data.overview.avg_message_length} ch`} />
                <Kpi label="Media" value={num(data.overview.media_messages)} tone="teal" />
                <Kpi label="Links" value={num(data.overview.links)} />
              </div>

              <div className="grid gap-3 xl:grid-cols-2">
                <Panel title="Hourly activity" subtitle={data.hourly.formula}>
                  <Chart option={barOption(data.hourly.series.map((row) => row.bucket.slice(0, 2)), data.hourly.series.map((row) => row.count))} height={230} />
                </Panel>
                <Panel title="Weekday distribution">
                  <Chart option={barOption(data.weekday.series.map((row) => row.bucket.slice(0, 3)), data.weekday.series.map((row) => row.count), { color: "#a78bfa" })} height={230} />
                </Panel>
                <Panel title="Monthly volume">
                  <Chart option={lineOption(data.monthly.series.map((row) => row.bucket), data.monthly.series.map((row) => row.count))} height={230} />
                </Panel>
                <Panel title="Weekly volume">
                  <Chart option={lineOption(data.weekly.series.map((row) => row.bucket), data.weekly.series.map((row) => row.count), { color: "#60a5fa" })} height={230} />
                </Panel>
              </div>

              <Panel title="Activity heatmap" subtitle={data.heatmap.formula}>
                <Chart option={heatmapOption(data.heatmap.grid, data.heatmap.weekdays, data.heatmap.hours)} height={240} />
              </Panel>

              <div className="grid gap-3 lg:grid-cols-3">
                <Panel title="Inactivity periods" dense>
                  <div className="p-2">
                    {(data.daily.inactivity?.longest_gaps ?? []).slice(0, 6).map((gap) => (
                      <div key={`${gap.from}-${gap.to}`} className="flex items-center justify-between border-b border-line/50 py-1 text-[11.5px] last:border-0">
                        <span className="text-muted">
                          {gap.from} → {gap.to}
                        </span>
                        <Badge tone={gap.days > 30 ? "amber" : "default"}>{gap.days} d</Badge>
                      </div>
                    ))}
                    {(data.daily.inactivity?.longest_gaps ?? []).length === 0 ? (
                      <p className="p-2 text-[11px] text-muted">No gaps longer than a week.</p>
                    ) : null}
                    <p className="mt-1 text-[10px] text-muted">{data.daily.inactivity?.method}</p>
                  </div>
                </Panel>

                <Panel title="Message bursts" dense>
                  <div className="p-2">
                    {(data.daily.bursts ?? []).map((burst) => (
                      <div key={burst.date} className="flex items-center justify-between border-b border-line/50 py-1 text-[11.5px] last:border-0">
                        <span className="text-muted">{burst.date}</span>
                        <span className="text-ink">
                          {num(burst.count)} <span className="text-muted">(z {burst.z})</span>
                        </span>
                      </div>
                    ))}
                    {(data.daily.bursts ?? []).length === 0 ? <p className="p-2 text-[11px] text-muted">No statistical bursts.</p> : null}
                  </div>
                </Panel>

                <Panel title="Longest sessions" dense>
                  <div className="p-2">
                    {data.sessions.sessions.slice(0, 6).map((session, index) => (
                      <div key={index} className="border-b border-line/50 py-1 text-[11px] last:border-0">
                        <p className="text-ink">
                          {num(session.messages)} messages · {session.minutes} min
                        </p>
                        <p className="text-muted">{dateTime(session.start)}</p>
                      </div>
                    ))}
                    <p className="mt-1 text-[10px] text-muted">
                      Sessions split at gaps over {data.sessions.gap_minutes} minutes.
                    </p>
                  </div>
                </Panel>
              </div>

              <div className="grid gap-3 lg:grid-cols-2">
                <Panel title="Most frequent terms" subtitle={data.words.formula}>
                  <Chart option={barOption(data.words.words.slice(0, 14).map((w) => w.word), data.words.words.slice(0, 14).map((w) => w.count), { horizontal: true })} height={280} />
                </Panel>
                <Panel title="Emoji usage" subtitle={`${num(data.emojis.total)} occurrences`}>
                  {data.emojis.emojis.length ? (
                    <div className="flex flex-wrap gap-1.5">
                      {data.emojis.emojis.map((item) => (
                        <span key={item.emoji} className="chip text-[13px]">
                          {item.emoji} <span className="text-[10.5px] text-muted">{item.count}</span>
                        </span>
                      ))}
                    </div>
                  ) : (
                    <EmptyState title="No emoji found" />
                  )}
                  <p className="mt-2 text-[10.5px] text-muted">{data.languages.method}</p>
                  <div className="mt-2 flex flex-wrap gap-1">
                    {data.languages.languages.map((language) => (
                      <Badge key={language.language}>
                        {language.language} · {num(language.count)}
                      </Badge>
                    ))}
                  </div>
                </Panel>
              </div>
            </div>
          ) : tab === "response" ? (
            <div className="space-y-3">
              <div className="grid grid-cols-2 gap-2 md:grid-cols-4">
                <Kpi label="Response pairs" value={num(data.response.samples)} tone="accent" />
                <Kpi label="Median response" value={data.response.median_minutes !== null ? `${data.response.median_minutes} min` : "—"} />
                <Kpi label="Average" value={data.response.average_minutes !== null ? `${data.response.average_minutes} min` : "—"} />
                <Kpi label="90th percentile" value={data.response.p90_minutes !== null ? `${data.response.p90_minutes} min` : "—"} />
              </div>

              <div className="grid gap-3 lg:grid-cols-2">
                <Panel title="Response-time distribution" subtitle="pairs inside a session, sender change required">
                  <Chart option={barOption(data.response.histogram.map((bucket) => bucket.label), data.response.histogram.map((bucket) => bucket.count), { color: "#2dd4bf" })} height={250} />
                </Panel>
                <Panel title="Methodology" dense>
                  <div className="space-y-1.5 p-3 text-[11.5px] leading-relaxed text-muted">
                    <p className="flex items-start gap-1.5">
                      <Timer className="mt-0.5 h-3.5 w-3.5 shrink-0 text-accent" />
                      Pair rule: {String(data.response.methodology.pair_rule)}.
                    </p>
                    <p>Session gap: {String(data.response.methodology.session_gap_minutes)} minutes.</p>
                    <p>Group chats: {String(data.response.methodology.group_chats)}.</p>
                    <p>System messages: {String(data.response.methodology.system_messages)}.</p>
                    <p>{num(data.response.excluded_session_breaks)} pairs were discarded because the gap exceeded the session boundary.</p>
                    <div className="pt-1">
                      {Object.entries(data.response.by_direction).map(([direction, stats]) => (
                        <p key={direction}>
                          {direction.replace("_", " ")}: {stats.samples} pairs · median {stats.median} min
                        </p>
                      ))}
                    </div>
                  </div>
                </Panel>
              </div>

              <Panel title="Response time by contact" dense>
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Contact</th>
                      <th>Median response</th>
                      <th>Samples</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.response.per_contact.map((row) => (
                      <tr key={row.contact_id}>
                        <td className="text-ink">{row.contact}</td>
                        <td>{row.median_minutes} min</td>
                        <td>{num(row.samples)}</td>
                      </tr>
                    ))}
                    {data.response.per_contact.length === 0 ? (
                      <tr>
                        <td colSpan={3} className="text-muted">
                          Not enough sender transitions to compute per-contact latency.
                        </td>
                      </tr>
                    ) : null}
                  </tbody>
                </table>
              </Panel>
            </div>
          ) : (
            <div className="space-y-3">
              {sentimentApi.data?.disabled ? (
                <Panel>
                  <EmptyState
                    icon={<Brain className="h-7 w-7" />}
                    title="Interpretive analysis is disabled"
                    description={sentimentApi.data.message ?? "Enable it in Settings → Forensic to see linguistic indicators."}
                  />
                </Panel>
              ) : null}
              {sentimentApi.loading ? <Spinner /> : null}
              {sentimentApi.error ? <ErrorState error={sentimentApi.error} onRetry={sentimentApi.reload} /> : null}
              {sentimentApi.data && !sentimentApi.data.disabled ? (
                <>
                  <div className="grid gap-2 md:grid-cols-3">
                    <Kpi label="Positive language" value={num(sentimentApi.data.counts?.positive)} tone="teal" hint={pct(sentimentApi.data.share?.positive ?? 0)} />
                    <Kpi label="Negative language" value={num(sentimentApi.data.counts?.negative)} tone="danger" hint={pct(sentimentApi.data.share?.negative ?? 0)} />
                    <Kpi label="Neutral" value={num(sentimentApi.data.counts?.neutral)} hint={pct(sentimentApi.data.share?.neutral ?? 0)} />
                  </div>
                  <Panel title="Sentiment trend" subtitle={sentimentApi.data.method}>
                    <Chart
                      option={lineOption(
                        (sentimentApi.data.series ?? []).map((row) => row.date.slice(5)),
                        (sentimentApi.data.series ?? []).map((row) => row.score),
                        { color: "#22d3ee" },
                      )}
                      height={230}
                    />
                    <p className="mt-1 text-[10.5px] text-muted">Score = (positive − negative) / total matched messages per day.</p>
                  </Panel>
                  <div className="grid gap-3 lg:grid-cols-2">
                    <Panel title="Emotional-language indicators" dense>
                      <div className="space-y-1 p-2">
                        {(sentimentApi.data.emotions ?? []).map((emotion) => (
                          <div key={emotion.emotion} className="border-b border-line/50 py-1.5 last:border-0">
                            <div className="flex items-center justify-between text-[11.5px]">
                              <span className="text-ink">{emotion.emotion}</span>
                              <span className="text-muted">{num(emotion.count)}</span>
                            </div>
                            {emotion.examples[0] ? (
                              <p className="mt-0.5 line-clamp-1 text-[10.5px] text-muted">“{emotion.examples[0]}”</p>
                            ) : null}
                          </div>
                        ))}
                      </div>
                    </Panel>
                    <Panel title="Conversation tone" dense>
                      <table className="data-table">
                        <thead>
                          <tr>
                            <th>Conversation</th>
                            <th>Positive</th>
                            <th>Negative</th>
                            <th>Neutral</th>
                          </tr>
                        </thead>
                        <tbody>
                          {(sentimentApi.data.by_conversation ?? []).map((row) => (
                            <tr key={row.conversation}>
                              <td className="text-ink">{row.conversation}</td>
                              <td>{num(row.positive)}</td>
                              <td>{num(row.negative)}</td>
                              <td>{num(row.neutral)}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </Panel>
                  </div>
                  <p className="rounded-xl border border-amber/30 bg-amber/8 p-3 text-[11px] leading-relaxed text-amber">
                    {sentimentApi.data.disclaimer}
                  </p>
                </>
              ) : null}

              <Panel title="Anomalies & pattern deviations" subtitle="robust rolling baseline">
                <Anomalies caseId={caseId} />
              </Panel>
            </div>
          )
        ) : null}
      </div>
    </div>
  );
}

function Anomalies({ caseId }: { caseId: string }) {
  const api = useApi<{ findings: { kind: string; date: string; metric: string; observed: number; baseline_median: number; deviation: number; explanation: string }[]; sensitivity: number; method: string; disclaimer: string; baseline_days: number }>(
    caseId ? `/api/cases/${caseId}/anomalies` : null,
    [caseId],
  );
  if (api.loading) return <Spinner />;
  if (api.error) return <ErrorState error={api.error} onRetry={api.reload} />;
  if (!api.data) return null;
  return (
    <div>
      {api.data.findings.length === 0 ? (
        <EmptyState
          icon={<Activity className="h-6 w-6" />}
          title="No deviations above the threshold"
          description={api.data.method}
        />
      ) : (
        <div className="space-y-1.5">
          {api.data.findings.map((finding, index) => (
            <div key={index} className="rounded-lg border border-line bg-elevated/50 px-2.5 py-2">
              <div className="flex items-center justify-between gap-2">
                <span className="text-[12px] text-ink">{finding.kind.replace(/_/g, " ")}</span>
                <Badge tone={Math.abs(finding.deviation) > 5 ? "danger" : "amber"}>
                  deviation {finding.deviation}
                </Badge>
              </div>
              <p className="text-[11px] text-muted">{finding.explanation}</p>
            </div>
          ))}
          <p className="pt-1 text-[10.5px] text-muted">{api.data.disclaimer}</p>
        </div>
      )}
    </div>
  );
}
