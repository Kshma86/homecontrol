import { shortValue } from "../../formatters";

export function timeText(value) {
  if (!value) return "-";
  return new Date(value).toLocaleTimeString("en-GB", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  });
}

function durationText(ms) {
  if (!Number.isFinite(ms)) return "-";
  const total = Math.max(0, Math.ceil(ms / 1000));
  const minutes = Math.floor(total / 60);
  const seconds = total % 60;
  return `${minutes}:${String(seconds).padStart(2, "0")}`;
}

export function timeAfterMinutes(minutes = 2) {
  const target = new Date(Date.now() + Math.max(1, Number(minutes) || 2) * 60_000);
  return `${String(target.getHours()).padStart(2, "0")}:${String(target.getMinutes()).padStart(2, "0")}`;
}

export async function waitForX10CommandResult(api, command, previousTs = 0, timeoutMs = 8000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    await new Promise((resolve) => window.setTimeout(resolve, 350));
    const current = await api("/api/context/robot", {
      allowOkFalse: true,
      skipContextRefresh: true,
    });
    const result = current?.command_result;
    if (result?.command !== command || Number(result?.ts || 0) <= Number(previousTs || 0)) continue;
    if (result.ok === false) {
      throw new Error(`Robot rejected ${command}: ${result.message || "unknown error"}`);
    }
    return result;
  }
  throw new Error(`No robot confirmation received for ${command}`);
}

function timeToMinutes(value) {
  const match = /^(\d{1,2}):(\d{2})$/.exec(String(value || ""));
  if (!match) return null;
  const hours = Number(match[1]);
  const minutes = Number(match[2]);
  if (hours < 0 || hours > 23 || minutes < 0 || minutes > 59) return null;
  return hours * 60 + minutes;
}

export function dndMatch(windows = [], date = new Date()) {
  const nowMin = date.getHours() * 60 + date.getMinutes();
  return windows.find((item) => {
    if (!item.enabled) return false;
    const start = timeToMinutes(item.start);
    const end = timeToMinutes(item.end);
    if (start === null || end === null || start === end) return false;
    if (start < end) return nowMin >= start && nowMin < end;
    return nowMin >= start || nowMin < end;
  }) || null;
}

export function roomCleanPlan(status, nowMs) {
  if (!status || typeof status !== "object") return null;
  const active = status.active || {};
  const task = status.task || {};
  const statusText = status.status || "";
  const isPending = ["scheduled", "active", "schedule_saved"].includes(statusText);
  if (!isPending) {
    return { status: statusText || "-", label: statusText || "-", meta: "no pending room clean" };
  }

  let targetMs = null;
  if (active.created_ts && active.delay_min !== undefined) {
    targetMs = (Number(active.created_ts) + Number(active.delay_min) * 60) * 1000;
  } else if (active.start_time) {
    const [hours, minutes] = String(active.start_time).split(":").map(Number);
    if (Number.isFinite(hours) && Number.isFinite(minutes)) {
      const target = new Date(nowMs);
      target.setHours(hours, minutes, 0, 0);
      if (target.getTime() < nowMs - 60_000) target.setDate(target.getDate() + 1);
      targetMs = target.getTime();
    }
  } else if (task.time) {
    const [hours, minutes] = String(task.time).split(":").map(Number);
    if (Number.isFinite(hours) && Number.isFinite(minutes)) {
      const target = new Date(nowMs);
      target.setHours(hours, minutes, 0, 0);
      if (target.getTime() < nowMs - 60_000) target.setDate(target.getDate() + 1);
      targetMs = target.getTime();
    }
  }

  if (!targetMs) return { status: statusText || "-", label: statusText || "-", meta: "scheduled time unavailable" };
  const remaining = targetMs - nowMs;
  return {
    status: statusText,
    targetMs,
    label: remaining > 0 ? durationText(remaining) : "due",
    meta: `${timeText(targetMs)} start | ${statusText}`,
  };
}

export function shortPath(value, max = 44) {
  const text = String(value || "");
  const name = text.split("/").filter(Boolean).pop() || text;
  return shortValue(name, max);
}
