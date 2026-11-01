import { useState } from "react";
import { Plus, Trash2 } from "lucide-react";
import { usePolledContext } from "../../apiClient";
import { IconButton } from "../../uiPrimitives";
import { createNote, notesFromPayload, removeNote, saveNote } from "./notesApi";
import {
  EMPTY_NOTES,
  NOTE_STATUS_OPTIONS,
  deleteNoteFromCollection,
  noteDate,
  noteStatusClass,
  noteStatusLabel,
  noteTypeClass,
  noteTypeLabel,
  patchNoteInCollection,
} from "./notesState";

export default function Notes({ setToast, scope = "general", embedded = false }) {
  const [noteDraft, setNoteDraft] = useState({ type: "issues", text: "" });
  const [busy, setBusy] = useState("");
  const notesPath = scope === "mower" ? "/api/mower/notes" : "/api/context/notes";
  const { data: notesData, setData: setNotes, loading, refresh: loadNotes } = usePolledContext(notesPath, {
    mapPayload: notesFromPayload,
    onError: (err) => setToast(err.message),
  });
  const notes = notesData || EMPTY_NOTES;
  const allNotes = [
    ...(notes.issues || []).map((item) => ({ ...item, type: "issues" })),
    ...(notes.requests || []).map((item) => ({ ...item, type: "requests" })),
  ].sort((left, right) => {
    const statusOrder = { open: 1, ready: 2, testing: 3, tested: 4 };
    const leftStatus = left.status || (left.done ? "tested" : "open");
    const rightStatus = right.status || (right.done ? "tested" : "open");
    const statusDiff = (statusOrder[leftStatus] || 5) - (statusOrder[rightStatus] || 5);
    if (statusDiff) return statusDiff;
    const dateDiff = new Date(right.created_at || 0).getTime() - new Date(left.created_at || 0).getTime();
    if (dateDiff) return dateDiff;
    return Number(right.id || 0) - Number(left.id || 0);
  });
  const readyCount = allNotes.filter((item) => item.status === "ready").length;
  const testingCount = allNotes.filter((item) => item.status === "testing").length;
  const testedCount = allNotes.filter((item) => item.status === "tested" || item.done).length;

  async function addNote(event) {
    event.preventDefault();
    const type = noteDraft.type === "requests" ? "requests" : "issues";
    const text = String(noteDraft.text || "").trim();
    if (!text) return;
    setBusy("add-note");
    try {
      const data = await createNote(type, text, scope);
      setNotes(data.notes || EMPTY_NOTES);
      setNoteDraft((current) => ({ ...current, text: "" }));
      setToast(type === "issues" ? "Issue added" : "Request added");
    } catch (err) {
      setToast(err.message);
    } finally {
      setBusy("");
    }
  }

  async function updateNote(type, id, patch) {
    if ("text" in patch && !String(patch.text || "").trim()) {
      setToast("Note text is required");
      await loadNotes();
      return;
    }
    const previous = notes;
    setNotes((current) => patchNoteInCollection(current, type, id, patch));
    try {
      const data = await saveNote(id, patch, scope);
      setNotes(data.notes || previous);
    } catch (err) {
      setNotes(previous);
      setToast(err.message);
    }
  }

  function editNoteText(type, id, text) {
    setNotes((current) => patchNoteInCollection(current, type, id, { text }));
  }

  function editNoteComment(type, id, comment) {
    setNotes((current) => patchNoteInCollection(current, type, id, { comment }));
  }

  function growCommentField(event) {
    const field = event.currentTarget;
    field.style.height = "auto";
    field.style.height = `${Math.min(field.scrollHeight, Math.round(window.innerHeight * 0.55))}px`;
  }

  async function deleteNote(type, id) {
    const previous = notes;
    setBusy(`delete-${id}`);
    setNotes((current) => deleteNoteFromCollection(current, type, id));
    try {
      const data = await removeNote(id, scope);
      setNotes(data.notes || EMPTY_NOTES);
    } catch (err) {
      setNotes(previous);
      setToast(err.message);
    } finally {
      setBusy("");
    }
  }

  return (
    <section className={`notes-page ${embedded ? "notes-page-embedded" : ""}`.trim()}>
      <article className="panel notes-entry-panel">
        <div className="panel-head">
          <h2>{scope === "mower" ? "New Mower Note" : "New Note"}</h2>
          <span>{(notes.issues || []).length} issues | {(notes.requests || []).length} requests</span>
        </div>
        <form className="notes-entry-form" onSubmit={addNote}>
          <div className="mode-toggle notes-type-toggle">
            <button className={noteDraft.type !== "requests" ? "mode-btn active" : "mode-btn"} type="button" onClick={() => setNoteDraft((current) => ({ ...current, type: "issues" }))}>Issues</button>
            <button className={noteDraft.type === "requests" ? "mode-btn active" : "mode-btn"} type="button" onClick={() => setNoteDraft((current) => ({ ...current, type: "requests" }))}>Requests</button>
          </div>
          <textarea
            value={noteDraft.text}
            onChange={(event) => setNoteDraft((current) => ({ ...current, text: event.target.value }))}
            placeholder={scope === "mower" ? (noteDraft.type === "requests" ? "New mower request..." : "New mower issue...") : (noteDraft.type === "requests" ? "New request..." : "New issue...")}
          />
          <IconButton icon={Plus} type="submit" disabled={Boolean(busy)}>{busy === "add-note" ? "Adding" : "Add"}</IconButton>
        </form>
      </article>

      <section className="notes-grid">
        <article className="panel notes-panel">
          <div className="panel-head">
            <h2>{scope === "mower" ? "Mower Notes" : "Notes"}</h2>
            <span>{readyCount} kész | {testingCount} teszt | {testedCount} tesztelt | {allNotes.length} összes</span>
          </div>
          <div className="table-wrap notes-table-wrap">
            <table className="notes-table">
              <thead>
                <tr><th>Type</th><th>Status</th><th>Text</th><th>Comment</th><th>Created</th><th>Action</th></tr>
              </thead>
              <tbody>
                {loading ? (
                  <tr>
                    <td colSpan="6">Loading notes...</td>
                  </tr>
                ) : allNotes.length ? allNotes.map((item) => {
                  const type = item.type === "requests" ? "requests" : "issues";
                  const status = item.status || (item.done ? "tested" : "open");
                  return (
                    <tr className={`note-status-${noteStatusClass(status)} ${item.done ? "done" : ""}`} key={`${type}-${item.id}`}>
                      <td>
                        <span className={`status-pill note-type-pill ${noteTypeClass(type)}`}>{noteTypeLabel(type)}</span>
                      </td>
                      <td>
                        <span className={`status-pill note-status-pill ${noteStatusClass(status)}`}>{noteStatusLabel(status)}</span>
                        <select
                          className={`notes-status-select ${noteStatusClass(status)}`}
                          aria-label={`${noteTypeLabel(type)} status`}
                          value={status}
                          onChange={(event) => updateNote(type, item.id, { status: event.target.value })}
                        >
                          {NOTE_STATUS_OPTIONS.map((option) => <option value={option.value} key={option.value}>{option.label}</option>)}
                        </select>
                      </td>
                      <td>
                        <input
                          className="notes-row-input"
                          value={item.text || ""}
                          onChange={(event) => editNoteText(type, item.id, event.target.value)}
                          onBlur={(event) => updateNote(type, item.id, { text: event.target.value })}
                        />
                      </td>
                      <td>
                        <textarea
                          className="notes-row-comment"
                          rows={5}
                          value={item.comment || ""}
                          onChange={(event) => {
                            editNoteComment(type, item.id, event.target.value);
                            growCommentField(event);
                          }}
                          onFocus={growCommentField}
                          onBlur={(event) => updateNote(type, item.id, { comment: event.target.value })}
                          placeholder="Comment..."
                        />
                      </td>
                      <td>{noteDate(item.created_at)}</td>
                      <td>
                        <IconButton icon={Trash2} className="secondary notes-delete" type="button" disabled={busy === `delete-${item.id}`} onClick={() => deleteNote(type, item.id)}>
                          {busy === `delete-${item.id}` ? "Deleting" : "Delete"}
                        </IconButton>
                      </td>
                    </tr>
                  );
                }) : (
                  <tr>
                    <td colSpan="6">No notes</td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </article>
      </section>
    </section>
  );
}
