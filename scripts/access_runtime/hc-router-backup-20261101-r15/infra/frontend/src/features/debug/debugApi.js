import { api } from "../../apiClient";

export function fetchDebugLogSources() {
  return api("/api/debug/logs");
}

export function fetchDebugLog(key, tail) {
  return api(`/api/debug/logs/${encodeURIComponent(key)}?tail=${tail}`, { allowOkFalse: true });
}
