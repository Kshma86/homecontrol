import { api } from "../../apiClient";

export function fetchDocumentation() {
  return api("/api/documentation");
}

export function fetchAbout() {
  return api("/api/about");
}
