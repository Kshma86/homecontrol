export const EMPTY_NOTES = { issues: [], requests: [] };

export const NOTE_TABLES = [
  { type: "issues", title: "Issues" },
  { type: "requests", title: "Requests" },
];

export const NOTE_STATUS_OPTIONS = [
  { value: "open", label: "Open" },
  { value: "ready", label: "Kész" },
  { value: "testing", label: "Tesztelés alatt" },
  { value: "tested", label: "Kész és tesztelt" },
];

export function noteDate(value) {
  if (!value) return "-";
  return new Date(value).toLocaleString("en-GB", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" });
}

export function noteStatusLabel(status) {
  return NOTE_STATUS_OPTIONS.find((option) => option.value === status)?.label || "Open";
}

export function noteStatusClass(status) {
  return ["ready", "testing", "tested"].includes(status) ? status : "open";
}

export function noteTypeLabel(type) {
  return type === "requests" ? "Request" : "Issue";
}

export function noteTypeClass(type) {
  return type === "requests" ? "request" : "issue";
}

export function patchNoteInCollection(notes, type, id, patch) {
  return {
    ...notes,
    [type]: (notes[type] || []).map((item) => (item.id === id ? { ...item, ...patch } : item)),
  };
}

export function deleteNoteFromCollection(notes, type, id) {
  return {
    ...notes,
    [type]: (notes[type] || []).filter((item) => item.id !== id),
  };
}
