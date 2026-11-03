export function appendResourceHistory(current, payload, now = new Date()) {
  const ts = payload?.generated_at || now.toISOString();
  const next = [
    ...current,
    {
      ts,
      cpu_percent: payload?.cpu?.ok ? Number(payload.cpu.percent) : null,
      memory_percent: payload?.memory?.ok ? Number(payload.memory.percent) : null,
    },
  ].filter((row) => new Date(ts).getTime() - new Date(row.ts).getTime() <= 15 * 60_000);
  return next.slice(-180);
}
