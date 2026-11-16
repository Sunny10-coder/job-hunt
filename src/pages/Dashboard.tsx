import { ArrowUpRight, Bookmark, FileWarning, MessageSquare, ShieldAlert, Upload } from "lucide-react";
import { Link, useNavigate } from "react-router-dom";
import { Chart } from "@/components/charts/Chart";
import { PageBody, PageHeader } from "@/components/layout/PageHeader";
import {
  Badge,
  Button,
  EmptyState,
  ErrorState,
  Kpi,
  Panel,
  Spinner,
} from "@/components/ui/primitives";
import { barOption, heatmapOption, lineOption } from "@/lib/charts";
import { bytes, dateTime, num, pct, truncate } from "@/lib/format";
import { useCase } from "@/hooks/useCaseContext";
import { useApi } from "@/hooks/useApi";
import type { Dashboard as DashboardData } from "@/types";

export function Dashboard() {
  const { caseId, caseData, error: caseError } = useCase();
  const navigate = useNavigate();
  const { data, error, loading, reload } = useApi<DashboardData>(caseId ? `/api/cases/${caseId}/dashboard` : null, [caseId]);

  const overview = data?.overview;
  const hasMessages = (overview?.messages ?? 0) > 0;

  return (
    <div className="flex h-full min-h-0 flex-col">
      <PageHeader
        title={caseData ? caseData.name : "Investigation dashboard"}
        description={
          caseData
            ? `${caseData.description || "No description recorded"} · CASE-${String(caseData.case_number).padStart(4, "0")} · examiner ${caseData.examiner || "not recorded"}`
            : undefined
        }
        actions={
          <>
            <Button variant="ghost" onClick={() => navigate(`/cases/${caseId}/case`)}>
              Case file
            </Button>
            <Button variant="ghost" onClick={() => navigate(`/cases/${caseId}/recovery`)}>
              <ShieldAlert className="h-3.5 w-3.5" /> Recovery
            </Button>
            <Button variant="primary" onClick={() => navigate(`/cases/${caseId}/import`)}>
              <Upload className="h-3.5 w-3.5" /> Import evidence
            </Button>
          </>
        }
        badges={
          <>
            {caseData ? <Badge tone="accent">CASE-{String(caseData.case_number).padStart(4, "0")}</Badge> : null}
            {data && data.findings > 0 ? <Badge tone="amber">{num(data.findings)} recovery findings</Badge> : null}
          </>
        }
      />
      <PageBody className="p-4">
        {caseError ? <ErrorState error={caseError} /> : null}
        {loading && !data ? <Spinner label="Computing case statistics…" /> : null}
        {error ? <ErrorState error={error} onRetry={reload} /> : null}

        {data ? (
          <div className="space-y-3">
            <div className="grid grid-cols-2 gap-2 md:grid-cols-3 xl:grid-cols-6">
              <Kpi label="Messages" value={num(overview?.real_messages)} tone="accent" hint={`${num(overview?.system_messages)} system notices`} />
              <Kpi label="Conversations" value={num(overview?.conversations)} hint={`${num(overview?.groups)} groups`} />
              <Kpi label="Contacts" value={num(overview?.contacts)} hint={`${num(overview?.active_days)} active days`} />
              <Kpi label="In / out" value={`${num(overview?.incoming)} / ${num(overview?.outgoing)}`} tone="teal" hint={overview?.has_self_contact ? "device owner present" : "owner not in export"} />
              <Kpi label="Media messages" value={num(overview?.media_messages)} hint={`${num(overview?.voice_notes)} voice notes`} />
              <Kpi label="Avg / active day" value={overview?.avg_messages_per_active_day ?? "—"} hint={`avg ${overview?.avg_message_length ?? 0} chars`} />
            </div>

            {!hasMessages ? (
              <Panel>
                <EmptyState
                  icon={<MessageSquare className="h-8 w-8" />}
                  title="This case has no imported messages yet"
                  description="Import a WhatsApp text export or a media-inclusive ZIP archive to populate the dashboard, search index and analytics."
                  action={
                    <Button variant="primary" onClick={() => navigate(`/cases/${caseId}/import`)}>
                      <Upload className="h-3.5 w-3.5" /> Open import centre
                    </Button>
                  }
                />
              </Panel>
            ) : (
              <>
                <div className="grid gap-3 xl:grid-cols-[minmax(0,1.35fr)_minmax(0,1fr)]">
                  <Panel
                    title="Messages per day"
                    subtitle={overview?.first_at ? `${dateTime(overview.first_at)} → ${dateTime(overview.last_at)} (UTC)` : undefined}
                    actions={
                      <Button size="sm" variant="ghost" onClick={() => navigate(`/cases/${caseId}/analytics`)}>
                        Analytics <ArrowUpRight className="h-3.5 w-3.5" />
                      </Button>
                    }
                  >
                    <Chart
                      option={lineOption(
                        data.daily.map((row) => row.bucket.slice(5)),
                        data.daily.map((row) => row.count),
                      )}
                      height={220}
                    />
                  </Panel>

                  <Panel title="Hourly distribution" subtitle="UTC hour of the normalised timestamp">
                    <Chart
                      option={barOption(
                        data.hourly.map((row) => row.bucket.slice(0, 2)),
                        data.hourly.map((row) => row.count),
                      )}
                      height={220}
                    />
                  </Panel>
                </div>

                <div className="grid gap-3 xl:grid-cols-[minmax(0,1.35fr)_minmax(0,1fr)]">
                  <Panel title="Activity heatmap" subtitle="weekday × hour, all imported messages">
                    <Chart
                      option={heatmapOption(data.heatmap.grid, data.heatmap.weekdays, Array.from({ length: 24 }, (_, i) => String(i).padStart(2, "0")))}
                      height={210}
                    />
                  </Panel>

                  <Panel title="Most active contacts" dense>
                    <div className="divide-y divide-line/60">
                      {data.top_contacts.map((contact) => (
                        <button
                          key={contact.id}
                          className="flex w-full items-center gap-2 px-3 py-2 text-left hover:bg-elevated/60"
                          onClick={() => navigate(`/cases/${caseId}/contacts?contact=${contact.id}`)}
                        >
                          <span className="flex h-7 w-7 items-center justify-center rounded-full border border-line bg-elevated text-[10px] text-accent">
                            {contact.display_name.slice(0, 2).toUpperCase()}
                          </span>
                          <span className="min-w-0 flex-1">
                            <span className="block truncate text-[12.5px] text-ink">{contact.display_name}</span>
                            <span className="block text-[10.5px] text-muted">
                              {num(contact.messages)} messages · {num(contact.media_messages)} media
                            </span>
                          </span>
                          <span className="mono text-[11px] text-muted">{contact.active_hours.map((hour) => `${String(hour).padStart(2, "0")}h`).join(" ")}</span>
                        </button>
                      ))}
                      {data.top_contacts.length === 0 ? <EmptyState title="No contacts parsed" /> : null}
                    </div>
                  </Panel>
                </div>

                <div className="grid gap-3 lg:grid-cols-3">
                  <Panel title="Recent conversations" dense>
                    <div className="divide-y divide-line/60">
                      {data.conversations.map((conversation) => (
                        <button
                          key={conversation.id}
                          className="w-full px-3 py-2 text-left hover:bg-elevated/60"
                          onClick={() => navigate(`/cases/${caseId}/explorer?c=${conversation.id}`)}
                        >
                          <div className="flex items-center justify-between gap-2">
                            <span className="truncate text-[12.5px] text-ink">{conversation.title}</span>
                            <Badge tone={conversation.kind === "group" ? "teal" : "muted"}>{conversation.kind}</Badge>
                          </div>
                          <p className="mt-0.5 truncate text-[11px] text-muted">
                            {conversation.last_sender ? `${conversation.last_sender}: ` : ""}
                            {truncate(conversation.last_message ?? "", 60) || "no messages"}
                          </p>
                          <p className="mt-0.5 text-[10.5px] text-muted">
                            {num(conversation.message_count)} messages · {num(conversation.media_count)} media · last {dateTime(conversation.last_at)}
                          </p>
                        </button>
                      ))}
                      {data.conversations.length === 0 ? <EmptyState title="No conversations yet" /> : null}
                    </div>
                  </Panel>

                  <Panel title="Evidence inventory" dense actions={<Link to={`/cases/${caseId}/case`} className="text-[11px] text-accent hover:underline">manage</Link>}>
                    <div className="divide-y divide-line/60">
                      {data.evidence.map((item) => (
                        <div key={item.id} className="px-3 py-2">
                          <div className="flex items-center justify-between gap-2">
                            <span className="truncate text-[12px] text-ink">{item.original_name}</span>
                            <Badge>{item.source_type.replace("whatsapp_", "")}</Badge>
                          </div>
                          <p className="mono mt-0.5 truncate text-[10px] text-muted" title={item.sha256}>
                            {item.sha256.slice(0, 32)}…
                          </p>
                          <p className="text-[10.5px] text-muted">
                            {num(item.message_count)} messages · {bytes(0)} · imported {dateTime(item.imported_at)}
                          </p>
                        </div>
                      ))}
                      {data.evidence.length === 0 ? <EmptyState title="No evidence imported" /> : null}
                    </div>
                  </Panel>

                  <Panel title="Findings & annotations" dense>
                    <div className="space-y-1 p-2">
                      {data.bookmarks.slice(0, 4).map((bookmark) => (
                        <button
                          key={bookmark.id}
                          onClick={() => navigate(`/cases/${caseId}/explorer?m=${bookmark.id}`)}
                          className="surface-muted w-full px-2.5 py-2 text-left hover:border-amber/40"
                        >
                          <p className="flex items-center gap-1 text-[10.5px] text-amber">
                            <Bookmark className="h-3 w-3" /> {bookmark.label || "bookmarked"}
                          </p>
                          <p className="mt-0.5 line-clamp-2 text-[11.5px] text-ink">{truncate(bookmark.body ?? "", 110)}</p>
                        </button>
                      ))}
                      {data.notes.slice(0, 3).map((note) => (
                        <div key={note.id} className="surface-muted px-2.5 py-2">
                          <p className="text-[10.5px] text-teal">investigation note · {dateTime(note.created_at)}</p>
                          <p className="mt-0.5 line-clamp-2 text-[11.5px] text-ink">{note.body}</p>
                        </div>
                      ))}
                      {data.bookmarks.length === 0 && data.notes.length === 0 ? (
                        <EmptyState
                          icon={<FileWarning className="h-6 w-6" />}
                          title="No bookmarks or notes"
                          description="Bookmark messages while exploring and record observations; they appear here and in reports."
                        />
                      ) : null}
                      <Button variant="ghost" size="sm" className="w-full" onClick={() => navigate(`/cases/${caseId}/case`)}>
                        Open case file
                      </Button>
                    </div>
                  </Panel>
                </div>

                <Panel title="Quick actions">
                  <div className="flex flex-wrap gap-2">
                    {data.quick_actions.map((action) => (
                      <Button key={action.label} onClick={() => navigate(action.route.includes("/") ? `/cases/${caseId}/${action.route}` : `/cases/${caseId}/${action.route}`)}>
                        {action.label}
                      </Button>
                    ))}
                    <Button variant="ghost" onClick={() => navigate(`/cases/${caseId}/analytics`)}>
                      Response-time statistics
                    </Button>
                    <Button variant="ghost" onClick={() => navigate(`/cases/${caseId}/reports`)}>
                      Generate a report
                    </Button>
                  </div>
                  <p className="mt-2 text-[10.5px] text-muted">
                    Incoming/outgoing split uses the contact flagged as the device owner; engagement
                    metrics describe observed messages only ({pct(overview ? (overview.real_messages / Math.max(1, overview.messages)) * 100 : 0)} of records are real messages).
                  </p>
                </Panel>
              </>
            )}
          </div>
        ) : null}
      </PageBody>
    </div>
  );
}
