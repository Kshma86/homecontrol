import { api } from "../../apiClient";

export function fetchPerformanceContext() {
  return api("/api/context/performance");
}
