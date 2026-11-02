import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { createContextReadStore } from "./contextReads.mjs";

export const DEFAULT_GET_TIMEOUT_MS = 15000;

export async function readJsonResponse(response) {
  const text = await response.text();
  if (!text) {
    throw new Error(response.ok ? "Empty response from API" : `API temporarily unavailable (HTTP ${response.status})`);
  }
  try {
    return JSON.parse(text);
  } catch {
    const preview = text.replace(/\s+/g, " ").trim().slice(0, 120);
    throw new Error(response.ok ? "Invalid JSON response from API" : `HTTP ${response.status}: ${preview || "invalid API response"}`);
  }
}

export async function api(path, options = {}) {
  const { allowOkFalse = false, skipContextRefresh = false, signal, timeoutMs,
    ...fetchOptions } = options;
  const isGet = !fetchOptions.method || fetchOptions.method.toUpperCase() === "GET";
  const requestedLimit = Number(timeoutMs);
  const limit = isGet ? (Number.isFinite(requestedLimit) && requestedLimit > 0 ? requestedLimit : DEFAULT_GET_TIMEOUT_MS)
    : (Number.isFinite(requestedLimit) && requestedLimit > 0 ? requestedLimit : 0);
  const controller = new AbortController();
  let timer, onAbort;
  const cancelled = new Promise((_, reject) => {
    onAbort = () => {
      controller.abort();
      reject(Object.assign(new Error("Request aborted"), { name: "AbortError" }));
    };
    if (signal?.aborted) onAbort();
    else signal?.addEventListener("abort", onAbort, { once: true });
    if (limit > 0) timer = setTimeout(() => {
      controller.abort();
      reject(Object.assign(new Error("API GET időkorlát túllépve"), { name: "TimeoutError" }));
    }, limit);
  });
  let response, data;
  try {
    [response, data] = await Promise.race([
      (async () => {
        if (signal?.aborted) throw Object.assign(new Error("Request aborted"), { name: "AbortError" });
        const result = await fetch(path, { headers: { "Content-Type": "application/json" },
          ...fetchOptions, signal: controller.signal });
        return [result, await readJsonResponse(result)];
      })(), cancelled,
    ]);
  } finally {
    clearTimeout(timer);
    signal?.removeEventListener("abort", onAbort);
  }
  if (!response.ok || (data.ok === false && !allowOkFalse)) {
    const detail = data.error || data.message || `HTTP ${response.status}`;
    const prefix = [data.stage, data.code].filter(Boolean).join(" / ");
    const error = new Error(prefix ? `${prefix}: ${detail}` : detail);
    error.payload = data;
    throw error;
  }
  if (!skipContextRefresh) refreshContextReadAfter(data);
  return data;
}

export const contextReads = createContextReadStore((path, options) => api(path, {
  ...options, skipContextRefresh: true,
}));
const identityPayload = (payload) => payload;

function contextReadAfterPaths(data) {
  const paths = Array.isArray(data?.context?.read_after) ? data.context.read_after : [];
  return [...new Set(paths.filter((path) => typeof path === "string" && path.startsWith("/api/context/")))];
}

export function refreshContextReadAfter(data) {
  const paths = contextReadAfterPaths(data);
  if (!paths.length) return;
  paths.forEach((path) => {
    contextReads.read(path, { force: true }).catch(() => {});
  });
}

export function useContextRefresh(paths, handler) {
  const handlerRef = useRef(handler);
  useEffect(() => {
    handlerRef.current = handler;
  }, [handler]);
  const pathKey = Array.isArray(paths) ? paths.join("|") : "";
  const stablePaths = useMemo(() => Array.isArray(paths) ? paths : [], [pathKey]);
  useEffect(() => {
    let alive = true;
    const wrapped = (payload, path, generation) => {
      if (alive && contextReads.isCurrent(path, generation)) handlerRef.current(payload, path);
    };
    const unsubscribe = stablePaths.map((path) => contextReads.subscribe(path, wrapped));
    return () => {
      alive = false;
      unsubscribe.forEach((stop) => stop());
    };
  }, [stablePaths]);
}

export function usePolledContext(path, {
  initialData = null,
  intervalMs = 0,
  onError = null,
  mapPayload = identityPayload,
  refreshPaths = [path],
  refreshOnMount = true,
} = {}) {
  const hasInitialData = initialData !== null && initialData !== undefined;
  const [data, setData] = useState(initialData);
  const [loading, setLoading] = useState(!hasInitialData);
  const [error, setError] = useState("");
  const onErrorRef = useRef(onError);
  const mapPayloadRef = useRef(mapPayload);
  const lifetime = useRef({ path, alive: false, sequence: 0, controller: null });
  const displayedPath = useRef(path);
  if (lifetime.current.path !== path) {
    lifetime.current.controller?.abort();
    lifetime.current = { path, alive: false, sequence: lifetime.current.sequence + 1, controller: null };
  }

  useEffect(() => {
    onErrorRef.current = onError;
  }, [onError]);

  useEffect(() => {
    mapPayloadRef.current = mapPayload;
  }, [mapPayload]);

  const load = useCallback(async (silent = false) => {
    const owner = lifetime.current;
    if (!owner.alive || owner.path !== path) return null;
    const sequence = ++owner.sequence;
    owner.controller?.abort();
    const controller = new AbortController();
    owner.controller = controller;
    const current = () => owner === lifetime.current && owner.alive && owner.sequence === sequence;
    const silentLoad = silent === true;
    if (!silentLoad) setLoading(true);
    try {
      const value = await contextReads.read(path, { signal: controller.signal, maxAgeMs: silentLoad ? 2000 : 0 });
      if (current() && contextReads.isCurrent(path, value.generation)) {
        setData(mapPayloadRef.current(value.payload));
        setError("");
      }
      return value.payload;
    } catch (err) {
      if (current() && !["AbortError", "SupersededContextRead"].includes(err.name)) {
        setError(err.message);
        onErrorRef.current?.(err);
      }
      return null;
    } finally {
      if (current()) setLoading(false);
    }
  }, [path]);

  useEffect(() => {
    const owner = lifetime.current;
    owner.alive = true;
    if (displayedPath.current !== path) {
      displayedPath.current = path;
      setData(initialData);
    }
    setLoading(!hasInitialData);
    setError("");
    if (refreshOnMount && document.visibilityState === "visible") load(hasInitialData);
    const poll = () => {
      if (document.visibilityState === "visible") load(true);
    };
    const id = intervalMs ? window.setInterval(poll, intervalMs) : null;
    const handleVisibility = () => {
      if (document.visibilityState === "visible") load(true);
      else { owner.sequence += 1; owner.controller?.abort(); }
    };
    document.addEventListener("visibilitychange", handleVisibility);
    return () => {
      owner.alive = false;
      owner.sequence += 1;
      owner.controller?.abort();
      if (id !== null) window.clearInterval(id);
      document.removeEventListener("visibilitychange", handleVisibility);
    };
  }, [hasInitialData, intervalMs, load, refreshOnMount]);

  useContextRefresh(refreshPaths, (payload, refreshPath) => {
    if (!lifetime.current.alive || lifetime.current.path !== path || !refreshPaths.includes(refreshPath)) return;
    setData(mapPayloadRef.current(payload));
    setError("");
    setLoading(false);
  });

  return { data, setData, loading, setLoading, error, setError, refresh: load };
}
