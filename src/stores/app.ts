import { create } from "zustand";
import type { CaseSummary, Settings } from "@/types";

type Toast = { id: string; title: string; description?: string; tone: "info" | "success" | "error" };

interface AppState {
  cases: CaseSummary[];
  currentCase: CaseSummary | null;
  settings: Settings | null;
  engineReady: boolean;
  engineError: string | null;
  sidebarCollapsed: boolean;
  toasts: Toast[];
  recentCaseIds: string[];
  setCases: (cases: CaseSummary[]) => void;
  setCurrentCase: (value: CaseSummary | null) => void;
  setSettings: (settings: Settings) => void;
  patchSettings: (patch: Partial<Settings>) => void;
  setEngine: (ready: boolean, error?: string | null) => void;
  toggleSidebar: () => void;
  toast: (toast: Omit<Toast, "id">) => void;
  dismissToast: (id: string) => void;
}

const READ_KEY = "wfs.recentCases";
const UI_KEY = "wfs.ui";

function loadRecent(): string[] {
  try {
    return JSON.parse(localStorage.getItem(READ_KEY) ?? "[]") as string[];
  } catch {
    return [];
  }
}

function loadUi(): { theme?: "dark" | "light"; density?: "comfortable" | "compact" } {
  try {
    return JSON.parse(localStorage.getItem(UI_KEY) ?? "{}");
  } catch {
    return {};
  }
}

export const useApp = create<AppState>((set, get) => ({
  cases: [],
  currentCase: null,
  settings: null,
  engineReady: false,
  engineError: null,
  sidebarCollapsed: false,
  toasts: [],
  recentCaseIds: loadRecent(),
  setCases: (cases) => set({ cases }),
  setCurrentCase: (value) => {
    if (!value) {
      set({ currentCase: null });
      return;
    }
    const recent = [value.id, ...get().recentCaseIds.filter((id) => id !== value.id)].slice(0, 8);
    localStorage.setItem(READ_KEY, JSON.stringify(recent));
    set({ currentCase: value, recentCaseIds: recent });
  },
  setSettings: (settings) => {
    const ui = loadUi();
    const theme = settings.theme ?? ui.theme ?? "dark";
    const density = settings.density ?? ui.density ?? "comfortable";
    document.documentElement.dataset.theme = theme;
    document.documentElement.dataset.density = density;
    document.documentElement.classList.toggle("dark", theme === "dark");
    localStorage.setItem(UI_KEY, JSON.stringify({ theme, density }));
    set({ settings });
  },
  patchSettings: (patch) => {
    const current = get().settings;
    if (!current) return;
    const next = { ...current, ...patch } as Settings;
    if (patch.theme || patch.density) {
      document.documentElement.dataset.theme = next.theme;
      document.documentElement.dataset.density = next.density;
      document.documentElement.classList.toggle("dark", next.theme === "dark");
      localStorage.setItem(UI_KEY, JSON.stringify({ theme: next.theme, density: next.density }));
    }
    set({ settings: next });
  },
  setEngine: (ready, error = null) => set({ engineReady: ready, engineError: error }),
  toggleSidebar: () => set({ sidebarCollapsed: !get().sidebarCollapsed }),
  toast: (toast) => {
    const id = Math.random().toString(36).slice(2);
    set({ toasts: [...get().toasts, { ...toast, id }] });
    window.setTimeout(() => {
      set({ toasts: get().toasts.filter((item) => item.id !== id) });
    }, 5200);
  },
  dismissToast: (id) => set({ toasts: get().toasts.filter((item) => item.id !== id) }),
}));
