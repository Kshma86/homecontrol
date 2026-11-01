import { useEffect, useRef, useState } from "react";
import { currentState } from "./mowerV3Model.mjs";
import { canClaimManual, fullSetpoint, MANUAL_PROTOCOL, manualStateInvalid, newRequestId, validLease } from "./mowerV3Controls.mjs";

export default function useMowerManual({ snapshot, receivedAt, error, authenticated, refresh }) {
  const [session, setSession] = useState({ phase: "DISCONNECTED", lease: null, observed: null, message: "Nincs kézi kapcsolat." });
  const [held, setHeld] = useState(false);
  const [intent, setIntentState] = useState({ linear: 0, yaw: 0, left: 0, right: 0, third: 0, thirdEnabled: false });
  const socketRef = useRef(null);
  const leaseRef = useRef(null);
  const bindingRef = useRef(null);
  const sequenceRef = useRef(0);
  const stalledSince = useRef(null);
  const heldRef = useRef(false);
  const intentRef = useRef(intent);
  const latestRef = useRef({ snapshot, receivedAt, error, authenticated, refresh });
  latestRef.current = { snapshot, receivedAt, error, authenticated, refresh };

  function setIntent(next) { intentRef.current = next; setIntentState(next); }
  function zero() {
    heldRef.current = false; setHeld(false);
    setIntent({ linear: 0, yaw: 0, left: 0, right: 0, third: 0, thirdEnabled: false });
    const socket = socketRef.current, lease = leaseRef.current;
    if (socket?.readyState === WebSocket.OPEN && lease && socket.bufferedAmount === 0) {
      try { socket.send(JSON.stringify(fullSetpoint(lease, ++sequenceRef.current, { linear: 0, yaw: 0, left: 0, right: 0, third: 0, thirdEnabled: false }, false))); }
      catch { socket.close(); }
    }
  }
  function disconnect(message = "Kézi kapcsolat lezárva.") {
    zero();
    const socket = socketRef.current, lease = leaseRef.current;
    if (socket?.readyState === WebSocket.OPEN && lease && socket.bufferedAmount === 0) {
      try { socket.send(JSON.stringify({ type: "release", lease_id: lease.lease_id, control_epoch: lease.control_epoch })); }
      catch { /* Closing the socket lets the native matching lease expire. */ }
    }
    stalledSince.current = null;
    socketRef.current = null; leaseRef.current = null; bindingRef.current = null;
    socket?.close();
    setIntent({ linear: 0, yaw: 0, left: 0, right: 0, third: 0, thirdEnabled: false });
    setSession({ phase: "DISCONNECTED", lease: null, observed: null, message });
  }
  function connect() {
    const latest = latestRef.current;
    const view = currentState(latest.snapshot, latest.receivedAt, performance.now());
    if (socketRef.current || !latest.authenticated || latest.error || !canClaimManual(latest.snapshot, view.state) || !view.fresh) return;
    heldRef.current = false; sequenceRef.current = 0; leaseRef.current = null;
    setIntent({ linear: 0, yaw: 0, left: 0, right: 0, third: 0, thirdEnabled: false });
    const url = `${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/api/mower/v3/manual`;
    let socket;
    try { socket = new WebSocket(url, MANUAL_PROTOCOL); }
    catch { setSession((previous) => ({ ...previous, message: "A kézi kapcsolat nem indítható." })); return; }
    socketRef.current = socket;
    setSession({ phase: "CONNECTING", lease: null, observed: null, message: "Kapcsolódás a backendreléhez…" });
    socket.onopen = () => {
      if (socketRef.current !== socket) return;
      const current = latestRef.current;
      const evidence = currentState(current.snapshot, current.receivedAt, performance.now());
      if (!current.authenticated || current.error || !canClaimManual(current.snapshot, evidence.state) || !evidence.fresh) return disconnect("A roverazonosság időközben elavult.");
      bindingRef.current = { esp_boot: current.snapshot.identity.esp_boot, stm_boot: current.snapshot.identity.stm_boot };
      socket.send(JSON.stringify({ type: "claim", request_id: newRequestId(), esp_boot: current.snapshot.identity.esp_boot,
        stm_boot: current.snapshot.identity.stm_boot, control_epoch: evidence.state.control_epoch }));
      setSession((previous) => ({ ...previous, phase: "CLAIMING", message: "STM lease-visszaigazolásra várunk…" }));
    };
    socket.onmessage = (event) => {
      if (socketRef.current !== socket) return;
      try {
        if (typeof event.data !== "string" || event.data.length > 512) throw new Error();
        const frame = JSON.parse(event.data);
        if (validLease(frame) && leaseRef.current === null
            && (latestRef.current.snapshot?.simple_control === true || (frame.drive_mode === "ERPM") === (latestRef.current.snapshot?.capabilities?.manual_erpm === true))) {
          const latest = latestRef.current, evidence = currentState(latest.snapshot, latest.receivedAt, performance.now());
          if (!latest.authenticated || latest.error || !evidence.fresh
              || latest.snapshot?.identity?.esp_boot !== bindingRef.current?.esp_boot
              || latest.snapshot?.identity?.stm_boot !== bindingRef.current?.stm_boot) {
            disconnect("A rover közben újraindult vagy az állapota elavult; új kézi belépés szükséges."); return;
          }
          leaseRef.current = frame;
          setSession({ phase: "ACTIVE", lease: frame, observed: null, message: "STM lease elfogadva. Mozgáshoz tartsd nyomva a deadmant." });
        } else if (frame.type === "observed" && leaseRef.current === null
            && Number.isInteger(frame.lease_id) && frame.lease_id >= 0 && frame.lease_id <= 0xffffffff
            && Number.isInteger(frame.last_input_seq) && frame.last_input_seq >= 0 && frame.last_input_seq <= 0xffffffff
            && ["DISARMED", "IDLE", "MANUAL", "AUTO", "PAUSED", "FAULT", "MAINTENANCE"].includes(frame.state) && typeof frame.stopped === "boolean") {
          setSession((previous) => ({ ...previous, observed: frame })); // No lease, no drive authority.
        } else if (frame.type === "observed" && leaseRef.current !== null && frame.lease_id === 0 && frame.last_input_seq === 0
            && ["DISARMED", "IDLE", "AUTO", "PAUSED", "FAULT", "MAINTENANCE"].includes(frame.state) && typeof frame.stopped === "boolean") {
          disconnect(`Az STM lezárta a kézi munkamenetet: ${frame.state}. Új belépés szükséges.`);
          latestRef.current.refresh?.();
        } else if (frame.type === "observed" && frame.lease_id === leaseRef.current?.lease_id
            && Number.isInteger(frame.last_input_seq) && frame.last_input_seq >= 0 && frame.last_input_seq <= sequenceRef.current && typeof frame.stopped === "boolean") {
          setSession((previous) => ({ ...previous, observed: frame }));
          if (frame.state !== "MANUAL") disconnect(`Az STM kilépett a kézi módból: ${frame.state}.`);
        } else if (frame.type === "error") {
          disconnect(`A relé lezárta a kapcsolatot: ${frame.code || "UNKNOWN"}${frame.code === "ROVER_SOCKET_CLOSED" ? ` (WS ${frame.detail})` : ""}.`);
          latestRef.current.refresh?.();
        }
        else throw new Error();
      } catch { disconnect("Hibás kézi válasz; a kapcsolat lezárva."); }
    };
    socket.onerror = () => { if (socketRef.current === socket) disconnect("A kézi relé nem érhető el."); };
    socket.onclose = () => { if (socketRef.current === socket) disconnect("A kézi kapcsolat megszakadt. Újracsatlakozás csak külön indítással."); };
  }
  function hold() {
    if (!leaseRef.current || socketRef.current?.readyState !== WebSocket.OPEN) return;
    heldRef.current = true; setHeld(true);
  }
  useEffect(() => {
    const timer = window.setInterval(() => {
      const lease = leaseRef.current;
      if (!lease) return;
      const latest = latestRef.current;
      const evidence = currentState(latest.snapshot, latest.receivedAt, performance.now());
      if (!latest.authenticated || latest.error || !evidence.fresh || document.visibilityState !== "visible"
          || latest.snapshot.identity.esp_boot !== bindingRef.current?.esp_boot
          || latest.snapshot.identity.stm_boot !== bindingRef.current?.stm_boot) {
        disconnect(latest.error || (!evidence.fresh ? `A roverállapot elavult: ${evidence.effectiveAge ?? "ismeretlen"} ms.`
          : document.visibilityState !== "visible" ? "Az oldal háttérbe került." : "A rover bootja vagy a kezelői hozzáférés megváltozott.")); return;
      }
      const state = evidence.state;
      if (manualStateInvalid(state, lease)) {
        disconnect("Az STM állapotváltása érvénytelenítette a kézi lease-t."); return;
      }
      const socket = socketRef.current;
      if (socket?.readyState !== WebSocket.OPEN) {
        disconnect("A kézi kapcsolat megszakadt."); return;
      }
      if (socket.bufferedAmount > 0) {
        if (stalledSince.current === null) stalledSince.current = performance.now();
        if (socket.bufferedAmount <= 1024 && performance.now() - stalledSince.current < 100) return;

        disconnect("A kézi küldés elakadt; a kapcsolat lezárva."); return;
      }
      stalledSince.current = null;
      try { socket.send(JSON.stringify(fullSetpoint(lease, ++sequenceRef.current, intentRef.current, heldRef.current))); }
      catch { disconnect("Érvénytelen kézi parancs."); }
    }, 75);
    const blur = () => zero();
    const hide = () => { if (document.visibilityState !== "visible") disconnect("Az oldal háttérbe került."); };
    window.addEventListener("blur", blur);
    document.addEventListener("visibilitychange", hide);
    return () => {
      window.clearInterval(timer);
      window.removeEventListener("blur", blur);
      document.removeEventListener("visibilitychange", hide);
      // Only matching manual release; leaving this tab never sends global STOP.
      const socket = socketRef.current, lease = leaseRef.current;
      heldRef.current = false;
      if (socket?.readyState === WebSocket.OPEN && lease && socket.bufferedAmount === 0) {
        try {
          socket.send(JSON.stringify(fullSetpoint(lease, ++sequenceRef.current, { linear: 0, yaw: 0, left: 0, right: 0, third: 0, thirdEnabled: false }, false)));
          socket.send(JSON.stringify({ type: "release", lease_id: lease.lease_id, control_epoch: lease.control_epoch }));
        } catch { /* Native lease expiry remains the disconnect backstop. */ }
      }
      socketRef.current = null; leaseRef.current = null; bindingRef.current = null;
      socket?.close();
    };
  }, []);
  return { ...session, held, intent, setIntent, connect, disconnect, hold, zero };
}
