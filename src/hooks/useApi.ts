import * as React from "react";
import { get } from "@/lib/api";

export interface ApiState<T> {
  data: T | null;
  error: string | null;
  loading: boolean;
  reload: () => void;
}

/** Small fetch hook with abort handling and manual refresh. */
export function useApi<T>(path: string | null, deps: unknown[] = []): ApiState<T> {
  const [data, setData] = React.useState<T | null>(null);
  const [error, setError] = React.useState<string | null>(null);
  const [loading, setLoading] = React.useState<boolean>(Boolean(path));
  const [nonce, setNonce] = React.useState(0);
  const controllerRef = React.useRef<AbortController | null>(null);

  React.useEffect(() => {
    if (!path) {
      setData(null);
      setLoading(false);
      return;
    }
    controllerRef.current?.abort();
    const controller = new AbortController();
    controllerRef.current = controller;
    setLoading(true);
    setError(null);
    get<T>(path, controller.signal)
      .then((payload) => {
        if (!controller.signal.aborted) {
          setData(payload);
          setLoading(false);
        }
      })
      .catch((err: Error) => {
        if (controller.signal.aborted) return;
        setError(err.message);
        setLoading(false);
      });
    return () => controller.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [path, nonce, ...deps]);

  const reload = React.useCallback(() => setNonce((value) => value + 1), []);
  return { data, error, loading, reload };
}

/** Poll an import/analysis job until it reaches a terminal state. */
export function useJob(jobId: string | null, onDone?: (status: string) => void) {
  const [job, setJob] = React.useState<import("@/types").ImportJob | null>(null);
  const [error, setError] = React.useState<string | null>(null);
  const doneRef = React.useRef<string | null>(null);

  React.useEffect(() => {
    if (!jobId) {
      setJob(null);
      return;
    }
    let cancelled = false;
    let timer: number | undefined;
    const tick = async () => {
      try {
        const payload = await get<import("@/types").ImportJob>(`/api/jobs/${jobId}`);
        if (cancelled) return;
        setJob(payload);
        if (["done", "failed", "cancelled"].includes(payload.status)) {
          if (doneRef.current !== payload.status) {
            doneRef.current = payload.status;
            onDone?.(payload.status);
          }
          return;
        }
      } catch (err) {
        if (!cancelled) setError((err as Error).message);
      }
      timer = window.setTimeout(tick, 700);
    };
    tick();
    return () => {
      cancelled = true;
      if (timer) window.clearTimeout(timer);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [jobId]);

  return { job, error };
}

export function useDebounced<T>(value: T, delay = 250): T {
  const [debounced, setDebounced] = React.useState(value);
  React.useEffect(() => {
    const timer = window.setTimeout(() => setDebounced(value), delay);
    return () => window.clearTimeout(timer);
  }, [value, delay]);
  return debounced;
}
