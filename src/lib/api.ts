/**
 * Thin typed client for the local forensic engine.
 *
 * In the desktop build the Tauri shell starts the Python sidecar on loopback
 * and hands us `{ baseUrl, token }`; in the browser dev preview Vite proxies
 * `/api` to the same engine, so the base is empty.
 */
export type Json = Record<string, unknown>;

let baseUrl = "";
let authToken: string | null = null;

export function configureApi(config: { baseUrl?: string; token?: string | null }) {
  baseUrl = (config.baseUrl ?? "").replace(/\/$/, "");
  authToken = config.token ?? null;
}

export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const headers: Record<string, string> = { Accept: "application/json" };
  if (init?.body) headers["Content-Type"] = "application/json";
  if (authToken) headers["Authorization"] = `Bearer ${authToken}`;
  const response = await fetch(`${baseUrl}${path}`, { ...init, headers: { ...headers, ...(init?.headers as Record<string, string>) } });
  const text = await response.text();
  let payload: unknown = null;
  if (text) {
    try {
      payload = JSON.parse(text);
    } catch {
      payload = text;
    }
  }
  if (!response.ok) {
    const message =
      payload && typeof payload === "object" && "error" in (payload as Json)
        ? String((payload as Json).error)
        : `Request failed (${response.status})`;
    throw new ApiError(message, response.status);
  }
  return payload as T;
}

export function get<T>(path: string, signal?: AbortSignal): Promise<T> {
  return request<T>(path, { signal });
}

export function post<T>(path: string, body?: unknown): Promise<T> {
  return request<T>(path, { method: "POST", body: body === undefined ? undefined : JSON.stringify(body) });
}

export function patch<T>(path: string, body: unknown): Promise<T> {
  return request<T>(path, { method: "PATCH", body: JSON.stringify(body) });
}

export function del<T>(path: string): Promise<T> {
  return request<T>(path, { method: "DELETE" });
}

export function apiUrl(path: string): string {
  return `${baseUrl}${path}`;
}

export function withToken(path: string): string {
  if (!authToken) return apiUrl(path);
  return `${apiUrl(path)}${path.includes("?") ? "&" : "?"}token=${encodeURIComponent(authToken)}`;
}

export function query(params: Record<string, string | number | boolean | null | undefined>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === null || value === undefined || value === "") continue;
    search.set(key, String(value));
  }
  const text = search.toString();
  return text ? `?${text}` : "";
}
