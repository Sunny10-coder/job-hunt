import { GitCompare, Users } from "lucide-react";
import * as React from "react";
import { useSearchParams } from "react-router-dom";
import { Chart } from "@/components/charts/Chart";
import { PageHeader } from "@/components/layout/PageHeader";
import { Dialog } from "@/components/ui/dialog";
import { Badge, Button, EmptyState, ErrorState, Panel, Spinner } from "@/components/ui/primitives";
import { barOption, lineOption } from "@/lib/charts";
import { dateTime, num } from "@/lib/format";
import { useCase } from "@/hooks/useCaseContext";
import { useApi } from "@/hooks/useApi";
import { post } from "@/lib/api";
import type { Contact, ContactProfile } from "@/types";

export function ContactsPage() {
  const { caseId } = useCase();
  const [params, setParams] = useSearchParams();
  const selected = params.get("contact");
  const [compareOpen, setCompareOpen] = React.useState(false);
  const [compareIds, setCompareIds] = React.useState<string[]>([]);
  const [comparison, setComparison] = React.useState<{
    profiles: { contact_id: string; name: string; messages: number; media_messages: number; avg_length: number; active_hours: string[]; median_response_minutes: number | null; top_topics: string[] }[];
    hourly_matrix: number[][];
    note: string;
  } | null>(null);
  const [compareBusy, setCompareBusy] = React.useState(false);

  const contactsApi = useApi<Contact[]>(caseId ? `/api/cases/${caseId}/contacts` : null, [caseId]);
  const contacts = contactsApi.data ?? [];

  React.useEffect(() => {
    if (!selected && contacts.length > 0) {
      const next = new URLSearchParams(params);
      next.set("contact", contacts[0].id);
      setParams(next, { replace: true });
    }
  }, [contacts, selected, params, setParams]);

  const profileApi = useApi<ContactProfile>(caseId && selected ? `/api/cases/${caseId}/contacts/${selected}` : null, [caseId, selected]);

  const runCompare = async () => {
    setCompareBusy(true);
    try {
      setComparison(await post(`/api/cases/${caseId}/contacts/compare`, { contact_ids: compareIds }));
    } finally {
      setCompareBusy(false);
    }
  };

  return (
    <div className="flex h-full min-h-0 flex-col">
      <PageHeader
        title="Contact intelligence"
        description="Observed communication behaviour per contact. These are counts and distributions, not inferences about personality, intent or feelings."
        actions={
          <Button variant="ghost" onClick={() => setCompareOpen(true)}>
            <GitCompare className="h-3.5 w-3.5" /> Compare contacts
          </Button>
        }
        badges={<Badge>{num(contacts.length)} contacts</Badge>}
      />
      <div className="grid min-h-0 flex-1 grid-cols-[290px_minmax(0,1fr)]">
        <aside className="min-h-0 overflow-y-auto border-r border-line bg-panel/40 scroll-thin">
          {contactsApi.loading ? <Spinner /> : null}
          {contactsApi.error ? <ErrorState error={contactsApi.error} onRetry={contactsApi.reload} /> : null}
          {contacts.map((contact) => (
            <button
              key={contact.id}
              onClick={() => {
                const next = new URLSearchParams(params);
                next.set("contact", contact.id);
                setParams(next);
              }}
              className={`w-full border-b border-line/50 px-3 py-2 text-left hover:bg-elevated/60 ${selected === contact.id ? "bg-elevated" : ""}`}
            >
              <div className="flex items-center justify-between gap-2">
                <span dir="auto" className="truncate text-[12.5px] text-ink">{contact.display_name}</span>
                {contact.is_self ? <Badge tone="accent">owner</Badge> : null}
              </div>
              <p className="text-[10.5px] text-muted">
                {num(contact.messages)} messages · {num(contact.media_messages)} media
              </p>
              <p className="text-[10px] text-muted/80">
                {dateTime(contact.first_seen)} → {dateTime(contact.last_seen)}
              </p>
            </button>
          ))}
          {contacts.length === 0 && !contactsApi.loading ? <EmptyState title="No contacts" /> : null}
        </aside>

        <div className="min-h-0 overflow-y-auto p-4 scroll-thin">
          {profileApi.loading ? <Spinner label="Building contact profile…" /> : null}
          {profileApi.error ? <ErrorState error={profileApi.error} onRetry={profileApi.reload} /> : null}
          {profileApi.data ? (
            <div className="space-y-3">
              <div className="grid grid-cols-2 gap-2 md:grid-cols-4 xl:grid-cols-6">
                <Metric label="Messages" value={num(profileApi.data.messages)} />
                <Metric label="Conversations" value={num(profileApi.data.conversations)} />
                <Metric label="Media messages" value={num(profileApi.data.media_messages)} />
                <Metric label="Avg length" value={`${profileApi.data.avg_length} ch`} />
                <Metric label="Median reply" value={profileApi.data.response ? `${profileApi.data.response.median_minutes} min` : "—"} />
                <Metric label="Initiations" value={num(profileApi.data.conversation_initiations)} />
              </div>

              <div className="grid gap-3 lg:grid-cols-2">
                <Panel title="Hourly activity" subtitle="UTC hour of messages sent by this contact">
                  <Chart option={barOption(profileApi.data.hourly.map((row) => row.hour.slice(0, 2)), profileApi.data.hourly.map((row) => row.count))} height={200} />
                </Panel>
                <Panel title="Monthly volume">
                  <Chart option={lineOption(profileApi.data.monthly.map((row) => row.bucket), profileApi.data.monthly.map((row) => row.count))} height={200} />
                </Panel>
              </div>

              <div className="grid gap-3 lg:grid-cols-3">
                <Panel title="Top terms" dense>
                  <div className="space-y-1 p-2">
                    {profileApi.data.topics.slice(0, 12).map((topic) => (
                      <div key={topic.word} className="flex items-center justify-between text-[11.5px]">
                        <span className="truncate text-ink">{topic.word}</span>
                        <span className="text-muted">{num(topic.count)}</span>
                      </div>
                    ))}
                    {profileApi.data.topics.length === 0 ? <EmptyState title="No terms" /> : null}
                  </div>
                </Panel>

                <Panel title="Groups observed in" dense>
                  <div className="space-y-1 p-2">
                    {profileApi.data.groups.map((group) => (
                      <p key={group.id} dir="auto" className="truncate text-[11.5px] text-ink">
                        {group.title}
                      </p>
                    ))}
                    {profileApi.data.groups.length === 0 ? <p className="p-2 text-[11px] text-muted">No group participation recorded.</p> : null}
                  </div>
                </Panel>

                <Panel title="Emoji & tags" dense>
                  <div className="p-2">
                    <div className="mb-2 flex flex-wrap gap-1">
                      {profileApi.data.emojis.map((item) => (
                        <span key={item.emoji} className="chip">
                          {item.emoji} {item.count}
                        </span>
                      ))}
                      {profileApi.data.emojis.length === 0 ? <span className="text-[11px] text-muted">No emoji</span> : null}
                    </div>
                    <div className="flex flex-wrap gap-1">
                      {profileApi.data.tags.map((tag) => (
                        <span key={tag.tag} className="chip">
                          {tag.tag} · {tag.count}
                        </span>
                      ))}
                    </div>
                  </div>
                </Panel>
              </div>

              <p className="rounded-xl border border-line bg-elevated/50 p-3 text-[11px] leading-relaxed text-muted">
                {profileApi.data.interpretation_note}
              </p>
            </div>
          ) : (
            <EmptyState icon={<Users className="h-7 w-7" />} title="Select a contact" description="Profiles show first/last interaction, volume, active hours, response trend and recorded topics." />
          )}
        </div>
      </div>

      <Dialog
        open={compareOpen}
        onClose={() => setCompareOpen(false)}
        title="Compare contacts"
        description="Side-by-side comparison of observed message behaviour. Not a psychological comparison."
        width="lg"
        footer={
          <>
            <Button variant="ghost" onClick={() => setCompareOpen(false)}>
              Close
            </Button>
            <Button variant="primary" loading={compareBusy} disabled={compareIds.length < 2} onClick={() => void runCompare()}>
              Compare {compareIds.length || ""}
            </Button>
          </>
        }
      >
        <div className="mb-3 flex flex-wrap gap-2">
          {contacts.slice(0, 12).map((contact) => (
            <label key={contact.id} className="chip cursor-pointer">
              <input
                type="checkbox"
                className="mr-1 accent-cyan-400"
                checked={compareIds.includes(contact.id)}
                onChange={(event) =>
                  setCompareIds((current) =>
                    event.target.checked ? [...current, contact.id] : current.filter((id) => id !== contact.id),
                  )
                }
              />
              {contact.display_name}
            </label>
          ))}
        </div>
        {comparison ? (
          <div className="space-y-2">
            <div className="overflow-x-auto">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Contact</th>
                    <th>Messages</th>
                    <th>Media</th>
                    <th>Avg length</th>
                    <th>Active hours</th>
                    <th>Median reply</th>
                    <th>Top topics</th>
                  </tr>
                </thead>
                <tbody>
                  {comparison.profiles.map((profile) => (
                    <tr key={profile.contact_id}>
                      <td className="text-ink">{profile.name}</td>
                      <td>{num(profile.messages)}</td>
                      <td>{num(profile.media_messages)}</td>
                      <td>{profile.avg_length}</td>
                      <td className="mono text-[10.5px]">{profile.active_hours.join(", ") || "—"}</td>
                      <td>{profile.median_response_minutes ?? "—"}</td>
                      <td className="text-[10.5px] text-muted">{profile.top_topics.join(", ")}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="text-[10.5px] text-muted">{comparison.note}</p>
          </div>
        ) : (
          <p className="text-[11.5px] text-muted">Select two or more contacts, then run the comparison.</p>
        )}
      </Dialog>
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
