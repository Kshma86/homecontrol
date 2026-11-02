export const SERVICE_CONNECTIONS = {
  UNCONFIGURED: "Nincs beállítva", SERVICE_CONNECTED: "Szervizkapcsolat él",
  STM_UNAVAILABLE: "ESP elérhető · STM nem friss", BUSY: "Lekérés folyamatban",
  AUTH_FAILED: "Hitelesítési hiba", UNREACHABLE: "Rover nem érhető el",
  HTTP_ERROR: "Rover API-hiba", REDIRECT_BLOCKED: "Átirányítás elutasítva",
  INCOMPATIBLE_VERSION: "Eltérő szervizprotokoll", INVALID_RESPONSE: "Hibás szervizválasz",
  SETUP_ONLY: "Beállító AP · LAN-cím szükséges", SERVICE_ONLY: "Szerviz API nem támogatott",
  HC_UPDATE_PENDING: "HC frissítési zárolás", UPDATE_STORAGE_UNAVAILABLE: "Zárolás nem ellenőrizhető",
};

export function serviceView(snapshot, receivedAt, now, error = "") {
  const age = snapshot?.freshness?.effective_age_ms;
  const elapsed = Number.isFinite(receivedAt) && Number.isFinite(now) ? Math.max(0, now - receivedAt) : null;
  const effectiveAge = Number.isInteger(age) && age >= 0 && elapsed !== null ? age + elapsed : null;
  const service = snapshot?.service;
  const accepted = service?.mode === "FIRST_INSTALL_SERVICE" && service?.service_abi === 1
    && service.motion_permitted === false && service.applied === false && service.commissioned === false;
  const fresh = !error && accepted && snapshot?.connection?.status === "SERVICE_CONNECTED"
    && snapshot?.freshness?.fresh === true && effectiveAge !== null && effectiveAge <= 3000;
  return { fresh, effectiveAge, current: fresh ? service : null,
    connection: error ? "HC lekérdezési hiba" : SERVICE_CONNECTIONS[snapshot?.connection?.status] || "Kapcsolódás…" };
}
