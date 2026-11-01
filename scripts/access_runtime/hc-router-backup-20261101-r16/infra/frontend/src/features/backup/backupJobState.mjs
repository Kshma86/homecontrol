export function backupProgress(request, jobs = [], now = Date.now()) {
  if (!request) return null;
  const job = jobs.find((item) => item.run_id === request.run_id);
  const label = request.kind === "git" ? "Git snapshot" : request.kind === "local" ? "Local backup" : request.kind === "router" ? "Router backup" : "Full AI backup";
  if (job?.state === "completed") return { pending: false, success: true, archive: job.archive?.name, message: `${label} completed` };
  if (["failed", "interrupted"].includes(job?.state)) return { pending: false, success: false, message: `${label} ${job.state}: ${job.error || "check target results"}` };
  if (job?.state === "running") return { pending: true, message: `${label} running` };
  return { pending: true, message: now - request.requestedAt > 60000 ? `${label} queued; waiting for the backup to start` : `${label} queued` };
}
