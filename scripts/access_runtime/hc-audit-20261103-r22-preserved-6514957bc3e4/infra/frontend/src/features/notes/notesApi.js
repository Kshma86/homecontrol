import { api } from "../../apiClient";

export function notesFromPayload(payload = {}) {
  return {
    issues: payload.issues || [],
    requests: payload.requests || [],
  };
}

function notesBase(scope = "general") {
  return scope === "mower" ? "/api/mower/notes" : "/api/notes";
}

export function createNote(type, text, scope = "general") {
  return api(notesBase(scope), {
    method: "POST",
    body: JSON.stringify({ type, text }),
  });
}

export function saveNote(id, patch, scope = "general") {
  return api(`${notesBase(scope)}/${id}`, {
    method: "PUT",
    body: JSON.stringify(patch),
  });
}

export function removeNote(id, scope = "general") {
  return api(`${notesBase(scope)}/${id}`, { method: "DELETE" });
}
