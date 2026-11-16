/**
 * Thin bridge to the Tauri shell.
 *
 * Every helper degrades safely in the browser preview: `isDesktop()` is false,
 * commands are never invoked and callers get a falsy result they can render as
 * "desktop only". Nothing here runs automatically.
 */
import { configureApi } from "@/lib/api";

export interface EngineHandle {
  base_url: string;
  token: string | null;
  port: number;
}

export function isDesktop(): boolean {
  return (
    typeof window !== "undefined" &&
    Boolean((window as { __TAURI_INTERNALS__?: unknown }).__TAURI_INTERNALS__)
  );
}

async function invokeDesktop<T>(command: string, args?: Record<string, unknown>): Promise<T> {
  if (!isDesktop()) {
    throw new Error("This action is only available in the desktop application.");
  }
  const { invoke } = await import("@tauri-apps/api/core");
  return invoke<T>(command, args);
}

/** Reveal a generated report, export or backup in the OS file manager. */
export async function revealPath(path: string, reveal = true): Promise<boolean> {
  if (!path || !isDesktop()) return false;
  try {
    await invokeDesktop("open_path", { path, revealOnly: reveal });
    return true;
  } catch {
    return false;
  }
}

/** Start a replacement engine on a new port and repoint the API client at it. */
export async function restartEngine(): Promise<EngineHandle | null> {
  if (!isDesktop()) return null;
  const info = await invokeDesktop<EngineHandle>("restart_engine");
  configureApi({ baseUrl: info.base_url, token: info.token });
  return info;
}

const AI_KEY_ACCOUNT = "ai-api-key";

/** True when an external-provider key is present in the OS credential store. */
export async function hasStoredApiKey(): Promise<boolean> {
  if (!isDesktop()) return false;
  try {
    const value = await invokeDesktop<string | null>("read_secret", { account: AI_KEY_ACCOUNT });
    return Boolean(value);
  } catch {
    return false;
  }
}

/** Store a provider key in the OS credential store, never in the database. */
export async function saveApiKey(value: string): Promise<void> {
  await invokeDesktop("save_secret", { account: AI_KEY_ACCOUNT, value });
}

export async function clearApiKey(): Promise<void> {
  await invokeDesktop("delete_secret", { account: AI_KEY_ACCOUNT });
}
