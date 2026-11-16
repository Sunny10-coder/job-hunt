import * as React from "react";
import { HashRouter, Navigate, Route, Routes } from "react-router-dom";
import { AppShell } from "@/components/layout/AppShell";
import { configureApi, get } from "@/lib/api";
import { useApp } from "@/stores/app";
import { Button, Spinner } from "@/components/ui/primitives";
import type { CaseSummary, Settings } from "@/types";
import { Welcome } from "@/pages/Welcome";
import { Dashboard } from "@/pages/Dashboard";
import { ImportCenter } from "@/pages/ImportCenter";
import { Explorer } from "@/pages/Explorer";
import { ContactsPage } from "@/pages/Contacts";
import { GroupsPage } from "@/pages/Groups";
import { AnalyticsPage } from "@/pages/Analytics";
import { TimelinePage } from "@/pages/Timeline";
import { NetworkPage } from "@/pages/Network";
import { RecoveryPage } from "@/pages/Recovery";
import { MediaPage } from "@/pages/Media";
import { VoicePage } from "@/pages/Voice";
import { AssistantPage } from "@/pages/Assistant";
import { SearchPage } from "@/pages/SearchPage";
import { ReportsPage } from "@/pages/Reports";
import { CaseManagement } from "@/pages/CaseManagement";
import { SettingsPage } from "@/pages/Settings";

declare global {
  interface Window {
    __TAURI_INTERNALS__?: unknown;
  }
}

const wait = (ms: number) => new Promise((resolve) => window.setTimeout(resolve, ms));

async function connectEngine(): Promise<void> {
  if (typeof window !== "undefined" && window.__TAURI_INTERNALS__) {
    const { invoke } = await import("@tauri-apps/api/core");
    const info = await invoke<{ base_url: string; token: string | null }>("engine_info");
    configureApi({ baseUrl: info.base_url, token: info.token });
  }
  let lastError: Error | null = null;
  for (let attempt = 0; attempt < 25; attempt += 1) {
    try {
      const health = await get<{ ok: boolean }>("/api/health");
      if (health.ok) return;
    } catch (error) {
      lastError = error as Error;
      await wait(300);
    }
  }
  throw lastError ?? new Error("Forensic engine did not respond");
}

export default function App() {
  const { setCases, setSettings, setEngine, engineReady, engineError } = useApp();
  const [booted, setBooted] = React.useState(false);
  const [bootError, setBootError] = React.useState<string | null>(null);

  const bootstrap = React.useCallback(async () => {
    setBooted(false);
    setBootError(null);
    try {
      await connectEngine();
      const [settings, cases] = await Promise.all([
        get<Settings>("/api/settings"),
        get<CaseSummary[]>("/api/cases"),
      ]);
      setSettings(settings);
      setCases(cases);
      setEngine(true);
      setBooted(true);
    } catch (error) {
      const message = (error as Error).message;
      setBootError(message);
      setEngine(false, message);
      setBooted(true);
    }
  }, [setCases, setEngine, setSettings]);

  React.useEffect(() => {
    void bootstrap();
  }, [bootstrap]);

  if (!booted) {
    return (
      <div className="flex h-full items-center justify-center bg-bg">
        <div className="text-center">
          <p className="mb-2 text-[13px] font-medium text-ink">WhatsApp Forensic Studio AI</p>
          <Spinner label="Starting the local forensic engine…" />
          <p className="mt-1 text-[11px] text-muted">
            All processing stays on this computer.
          </p>
        </div>
      </div>
    );
  }

  return (
    <HashRouter>
      {!engineReady && bootError ? (
        <div className="mx-auto mt-16 max-w-lg rounded-2xl border border-danger/30 bg-danger/8 p-5">
          <h1 className="text-[14px] font-semibold text-danger">Forensic engine unavailable</h1>
          <p className="mt-1 text-[12px] leading-relaxed text-muted">{engineError ?? bootError}</p>
          <p className="mt-2 text-[11.5px] leading-relaxed text-muted">
            In development, start it with{" "}
            <code className="mono rounded bg-elevated px-1">python -m wfs_engine.cli serve --port 8765</code>{" "}
            from the <code className="mono">forensic-engine</code> folder. In the installed
            application the engine starts automatically.
          </p>
          <Button variant="primary" className="mt-3" onClick={() => void bootstrap()}>
            Retry connection
          </Button>
        </div>
      ) : (
        <Routes>
          <Route element={<AppShell />}>
            <Route index element={<Welcome />} />
            <Route path="settings" element={<SettingsPage />} />
            <Route path="cases/:caseId">
              <Route index element={<Dashboard />} />
              <Route path="import" element={<ImportCenter />} />
              <Route path="explorer" element={<Explorer />} />
              <Route path="contacts" element={<ContactsPage />} />
              <Route path="groups" element={<GroupsPage />} />
              <Route path="analytics" element={<AnalyticsPage />} />
              <Route path="timeline" element={<TimelinePage />} />
              <Route path="network" element={<NetworkPage />} />
              <Route path="recovery" element={<RecoveryPage />} />
              <Route path="media" element={<MediaPage />} />
              <Route path="voice" element={<VoicePage />} />
              <Route path="assistant" element={<AssistantPage />} />
              <Route path="search" element={<SearchPage />} />
              <Route path="reports" element={<ReportsPage />} />
              <Route path="case" element={<CaseManagement />} />
            </Route>
            <Route path="*" element={<Navigate to="/" replace />} />
          </Route>
        </Routes>
      )}
    </HashRouter>
  );
}
