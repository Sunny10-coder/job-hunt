import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function num(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  return new Intl.NumberFormat().format(value);
}

export function pct(value: number | null | undefined, digits = 1): string {
  if (value === null || value === undefined) return "—";
  return `${value.toFixed(digits)}%`;
}

export function bytes(value: number | null | undefined): string {
  if (!value) return "0 B";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let size = value;
  let unit = 0;
  while (size >= 1024 && unit < units.length - 1) {
    size /= 1024;
    unit += 1;
  }
  return `${size.toFixed(size >= 10 || unit === 0 ? 0 : 1)} ${units[unit]}`;
}

const DAY = 24 * 60 * 60 * 1000;

export function dateTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const date = new Date(iso.endsWith("Z") ? iso : `${iso}Z`);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleString(undefined, {
    year: "numeric",
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function dateOnly(iso: string | null | undefined): string {
  if (!iso) return "—";
  const date = new Date(iso.endsWith("Z") ? iso : `${iso}Z`);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleDateString(undefined, { year: "numeric", month: "short", day: "2-digit" });
}

export function timeOnly(iso: string | null | undefined): string {
  if (!iso) return "—";
  const date = new Date(iso.endsWith("Z") ? iso : `${iso}Z`);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });
}

export function relative(iso: string | null | undefined): string {
  if (!iso) return "—";
  const date = new Date(iso.endsWith("Z") ? iso : `${iso}Z`);
  const diff = Date.now() - date.getTime();
  if (Number.isNaN(diff)) return iso;
  if (diff < 60_000) return "just now";
  if (diff < 3_600_000) return `${Math.round(diff / 60_000)}m ago`;
  if (diff < DAY) return `${Math.round(diff / 3_600_000)}h ago`;
  if (diff < 30 * DAY) return `${Math.round(diff / DAY)}d ago`;
  return dateOnly(iso);
}

export function truncate(text: string, max = 90): string {
  if (!text) return "";
  return text.length > max ? `${text.slice(0, max - 1)}…` : text;
}

export function initials(name: string): string {
  return name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase() ?? "")
    .join("");
}

/** Colour-stable avatar tint derived from the name (never content-based). */
export function avatarTint(name: string): string {
  const palette = ["#22d3ee", "#2dd4bf", "#a78bfa", "#f59e0b", "#f472b6", "#60a5fa"];
  let hash = 0;
  for (let i = 0; i < name.length; i += 1) hash = (hash * 31 + name.charCodeAt(i)) % 997;
  return palette[hash % palette.length];
}

/** Render engine highlight markers (\u0002…\u0003) as React-safe parts. */
export function splitHighlights(snippet: string): { text: string; hit: boolean }[] {
  const parts: { text: string; hit: boolean }[] = [];
  let buffer = "";
  let hit = false;
  for (const char of snippet) {
    if (char === "\u0002") {
      if (buffer) parts.push({ text: buffer, hit });
      buffer = "";
      hit = true;
    } else if (char === "\u0003") {
      if (buffer) parts.push({ text: buffer, hit });
      buffer = "";
      hit = false;
    } else {
      buffer += char;
    }
  }
  if (buffer) parts.push({ text: buffer, hit });
  return parts;
}
