export function bringupView(snapshot, receivedAt, now, error = "") {
  const valid = snapshot?.mode === "HC_BRINGUP" && snapshot?.read_only === true
    && snapshot?.identity?.mode === "HC_BRINGUP" && snapshot.identity.motion_permitted === false
    && snapshot.identity.commissioned === false;
  const elapsed = Number.isFinite(receivedAt) && Number.isFinite(now) && now >= receivedAt ? now - receivedAt : null;
  function current(freshness, limit) {
    const age = freshness?.effective_age_ms;
    const effectiveAge = Number.isInteger(age) && age >= 0 && elapsed !== null ? age + elapsed : null;
    return { effectiveAge, fresh: valid && !error && freshness?.fresh === true
      && effectiveAge !== null && effectiveAge <= limit };
  }
  const source = current(snapshot?.freshness, 1500), network = current(snapshot?.health_freshness, 3000);
  const fresh = source.fresh && snapshot?.connection?.status === "BRINGUP_CONNECTED";
  return { fresh, effectiveAge: source.effectiveAge, state: fresh ? snapshot.state : null,
    health: network.fresh ? snapshot.health : null,
    connection: error ? "HC nem érhető el" : fresh ? "HC kapcsolat működik" : snapshot?.connection?.status === "STALE"
      || snapshot?.connection?.status === "BRINGUP_CONNECTED" ? "Elavult STM-adat" : snapshot?.connection?.status || "Kapcsolódás…" };
}
