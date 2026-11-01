export function aiPowerStatus(guard = {}, now = Date.now()) {
  const known = guard.guard_known !== false && typeof guard.backup_running === "boolean";
  const queued = Boolean(guard.deferred_shutdown);
  const pending = guard.pending_power_off;
  const due = Number(pending?.due_at_epoch || 0) * 1000;
  const remainingSec = known && pending && Number.isFinite(due) ? Math.max(0, Math.ceil((due - now) / 1000)) : 0;
  const label = !known ? "Unknown" : guard.backup_running ? "Backup running" : queued ? "Shutdown queued" : pending ? "Power off scheduled" : "Clear";
  return { known, queued, label, remainingSec, warn: !known || Boolean(guard.backup_running) || queued || Boolean(pending) };
}
