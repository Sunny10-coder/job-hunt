import {
  Activity,
  Archive,
  AudioLines,
  BarChart3,
  BookMarked,
  Bot,
  ChevronLeft,
  ChevronRight,
  FileText,
  FolderOpen,
  Gauge,
  Image as ImageIcon,
  LayoutDashboard,
  MessageSquare,
  Moon,
  Network,
  Search,
  Settings as SettingsIcon,
  ShieldAlert,
  Sun,
  Upload,
  Users,
} from "lucide-react";
import * as React from "react";
import { Link, NavLink, Outlet, useLocation, useNavigate, useParams } from "react-router-dom";
import { apiUrl, patch } from "@/lib/api";
import { cn } from "@/lib/format";
import { useApp } from "@/stores/app";
import { Badge, Button, Select } from "@/components/ui/primitives";

interface NavItem {
  to: string;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
}

const INVESTIGATION: NavItem[] = [
  { to: "", label: "Dashboard", icon: LayoutDashboard },
  { to: "explorer", label: "Conversations", icon: MessageSquare },
  { to: "search", label: "Advanced search", icon: Search },
  { to: "timeline", label: "Timeline", icon: Activity },
];

const INTELLIGENCE: NavItem[] = [
  { to: "contacts", label: "Contacts", icon: Users },
  { to: "groups", label: "Groups", icon: Users },
  { to: "analytics", label: "Analytics", icon: BarChart3 },
  { to: "network", label: "Network", icon: Network },
  { to: "assistant", label: "AI assistant", icon: Bot },
];

const EVIDENCE: NavItem[] = [
  { to: "import", label: "Import centre", icon: Upload },
  { to: "media", label: "Media forensics", icon: ImageIcon },
  { to: "voice", label: "Voice intelligence", icon: AudioLines },
  { to: "recovery", label: "Recovery analysis", icon: ShieldAlert },
];

const DELIVERY: NavItem[] = [
  { to: "reports", label: "Reports & exports", icon: FileText },
  { to: "case", label: "Case management", icon: BookMarked },
];

function SidebarLink({ item, caseId, collapsed }: { item: NavItem; caseId: string; collapsed: boolean }) {
  const Icon = item.icon;
  return (
    <NavLink
      to={`/cases/${caseId}${item.to ? `/${item.to}` : ""}`}
      end={item.to === ""}
      title={collapsed ? item.label : undefined}
      className={({ isActive }) =>
        cn("nav-item", isActive && "nav-item-active", collapsed && "justify-center px-0")
      }
    >
      <Icon className="h-4 w-4 shrink-0" />
      {!collapsed ? <span className="truncate">{item.label}</span> : null}
    </NavLink>
  );
}

export function AppShell() {
  const { caseId } = useParams<{ caseId: string }>();
  const location = useLocation();
  const navigate = useNavigate();
  const { cases, currentCase, settings, engineReady, engineError, sidebarCollapsed, toggleSidebar, patchSettings, toasts, dismissToast } =
    useApp();
  const [globalQuery, setGlobalQuery] = React.useState("");

  const themed = settings?.theme ?? "dark";
  const toggleTheme = async () => {
    const next = themed === "dark" ? "light" : "dark";
    patchSettings({ theme: next });
    if (currentCase) {
      try {
        await patch("/api/settings", { theme: next });
      } catch {
        /* theme is local-first; a failed persist is not fatal */
      }
    }
  };

  const submitSearch = (event: React.FormEvent) => {
    event.preventDefault();
    if (!caseId || !globalQuery.trim()) return;
    navigate(`/cases/${caseId}/search?q=${encodeURIComponent(globalQuery.trim())}`);
  };

  return (
    <div className="flex h-full w-full overflow-hidden bg-bg">
      <aside
        className={cn(
          "flex h-full shrink-0 flex-col border-r border-line bg-navy transition-[width] duration-200",
          sidebarCollapsed ? "w-[62px]" : "w-[218px]",
        )}
      >
        <div className={cn("flex items-center gap-2 px-3 py-3", sidebarCollapsed && "justify-center px-0")}>
          <div className="flex h-8 w-8 items-center justify-center rounded-lg border border-accent/40 bg-accent/12">
            <Gauge className="h-4 w-4 text-accent" />
          </div>
          {!sidebarCollapsed ? (
            <div className="min-w-0">
              <p className="truncate text-[12.5px] font-semibold leading-tight text-ink">Forensic Studio</p>
              <p className="truncate text-[10px] uppercase tracking-[0.12em] text-muted">Local · offline</p>
            </div>
          ) : null}
        </div>

        <nav className="min-h-0 flex-1 space-y-3 overflow-y-auto px-2 pb-3 scroll-thin">
          {caseId ? (
            <>
              <NavGroup title="Investigation" collapsed={sidebarCollapsed}>
                {INVESTIGATION.map((item) => (
                  <SidebarLink key={item.to} item={item} caseId={caseId} collapsed={sidebarCollapsed} />
                ))}
              </NavGroup>
              <NavGroup title="Intelligence" collapsed={sidebarCollapsed}>
                {INTELLIGENCE.map((item) => (
                  <SidebarLink key={item.to} item={item} caseId={caseId} collapsed={sidebarCollapsed} />
                ))}
              </NavGroup>
              <NavGroup title="Evidence" collapsed={sidebarCollapsed}>
                {EVIDENCE.map((item) => (
                  <SidebarLink key={item.to} item={item} caseId={caseId} collapsed={sidebarCollapsed} />
                ))}
              </NavGroup>
              <NavGroup title="Delivery" collapsed={sidebarCollapsed}>
                {DELIVERY.map((item) => (
                  <SidebarLink key={item.to} item={item} caseId={caseId} collapsed={sidebarCollapsed} />
                ))}
              </NavGroup>
            </>
          ) : (
            <NavGroup title="Workspace" collapsed={sidebarCollapsed}>
              <NavLink to="/" end className={({ isActive }) => cn("nav-item", isActive && "nav-item-active", sidebarCollapsed && "justify-center px-0")}>
                <FolderOpen className="h-4 w-4" />
                {!sidebarCollapsed ? "Cases" : null}
              </NavLink>
              <NavLink to="/settings" className={({ isActive }) => cn("nav-item", isActive && "nav-item-active", sidebarCollapsed && "justify-center px-0")}>
                <SettingsIcon className="h-4 w-4" />
                {!sidebarCollapsed ? "Settings" : null}
              </NavLink>
            </NavGroup>
          )}
        </nav>

        <div className={cn("border-t border-line px-2 py-2", sidebarCollapsed && "px-1")}>
          {!sidebarCollapsed ? (
            <div className="mb-2 rounded-lg border border-line bg-panel px-2 py-1.5">
              <div className="flex items-center gap-1.5">
                <span
                  className={cn(
                    "h-1.5 w-1.5 rounded-full",
                    engineReady ? "bg-teal" : engineError ? "bg-danger" : "animate-pulse-soft bg-amber",
                  )}
                />
                <span className="text-[10.5px] text-muted">
                  {engineReady ? "Forensic engine ready" : engineError ? "Engine offline" : "Connecting…"}
                </span>
              </div>
            </div>
          ) : null}
          <div className={cn("flex items-center gap-1", sidebarCollapsed && "flex-col")}>
            <Button variant="ghost" size="icon" onClick={toggleTheme} title="Toggle theme">
              {themed === "dark" ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
            </Button>
            <Link to="/settings" className="flex-1">
              <Button variant="ghost" size="icon" title="Settings" className={cn(sidebarCollapsed ? "" : "w-full")}>
                <SettingsIcon className="h-4 w-4" />
              </Button>
            </Link>
            <Button variant="ghost" size="icon" onClick={toggleSidebar} title="Collapse sidebar">
              {sidebarCollapsed ? <ChevronRight className="h-4 w-4" /> : <ChevronLeft className="h-4 w-4" />}
            </Button>
          </div>
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-12 shrink-0 items-center gap-3 border-b border-line bg-panel/70 px-3 backdrop-blur">
          <div className="flex min-w-0 items-center gap-2">
            <Link to="/" className="text-[12px] text-muted hover:text-ink">
              Cases
            </Link>
            {currentCase ? (
              <>
                <span className="text-muted/50">/</span>
                <Select
                  aria-label="Select case"
                  className="h-7 w-[220px] text-[12px]"
                  value={currentCase.id}
                  onChange={(event) => navigate(`/cases/${event.target.value}`)}
                >
                  {cases.map((item) => (
                    <option key={item.id} value={item.id}>
                      CASE-{String(item.case_number).padStart(4, "0")} · {item.name}
                    </option>
                  ))}
                </Select>
                {currentCase.status === "archived" ? <Badge tone="amber">archived</Badge> : null}
              </>
            ) : null}
          </div>

          <form onSubmit={submitSearch} className="ml-auto flex w-full max-w-sm items-center gap-2">
            <div className="relative flex-1">
              <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted" />
              <input
                value={globalQuery}
                onChange={(event) => setGlobalQuery(event.target.value)}
                placeholder={caseId ? "Search this case…" : "Select a case to search"}
                disabled={!caseId}
                className="field h-8 pl-8 text-[12px]"
              />
            </div>
          </form>

          <div className="flex items-center gap-1.5">
            {currentCase ? (
              <Button
                variant="ghost"
                size="sm"
                onClick={() => window.open(apiUrl(`/api/cases/${currentCase.id}/manifest`), "_blank")}
                title="Open case manifest JSON"
              >
                <Archive className="h-3.5 w-3.5" /> Manifest
              </Button>
            ) : null}
            <Badge tone={engineReady ? "teal" : "danger"}>
              <span className={cn("h-1.5 w-1.5 rounded-full", engineReady ? "bg-teal" : "bg-danger")} />
              {engineReady ? "local" : "offline"}
            </Badge>
          </div>
        </header>

        <main className="min-h-0 flex-1 overflow-hidden">
          <Outlet />
        </main>
      </div>

      <div className="pointer-events-none fixed bottom-3 right-3 z-50 flex w-80 flex-col gap-2">
        {toasts.map((toast) => (
          <div
            key={toast.id}
            onClick={() => dismissToast(toast.id)}
            className={cn(
              "pointer-events-auto animate-fade-in cursor-pointer rounded-xl border px-3 py-2 shadow-pop backdrop-blur",
              toast.tone === "error"
                ? "border-danger/40 bg-danger/12"
                : toast.tone === "success"
                  ? "border-teal/40 bg-teal/12"
                  : "border-line bg-panel/95",
            )}
          >
            <p className="text-[12px] font-medium text-ink">{toast.title}</p>
            {toast.description ? (
              <p className="mt-0.5 text-[11px] leading-snug text-muted">{toast.description}</p>
            ) : null}
          </div>
        ))}
      </div>
      <span className="hidden">{location.pathname}</span>
    </div>
  );
}

function NavGroup({
  title,
  children,
  collapsed,
}: {
  title: string;
  children: React.ReactNode;
  collapsed: boolean;
}) {
  return (
    <div>
      {!collapsed ? (
        <p className="mb-1 px-2 text-[9.5px] font-semibold uppercase tracking-[0.16em] text-muted/70">{title}</p>
      ) : (
        <div className="mx-2 mb-1 border-t border-line/60" />
      )}
      <div className="space-y-0.5">{children}</div>
    </div>
  );
}
