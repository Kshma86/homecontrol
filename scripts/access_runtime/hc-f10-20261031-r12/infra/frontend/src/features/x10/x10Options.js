import { textValue } from "../../formatters";

export const x10ModeOptions = [
  { value: "0", label: "Vacuum" },
  { value: "1", label: "Mop" },
  { value: "2", label: "Vacuum + Mop" },
];

export const x10SuctionOptions = [
  { value: "0", label: "Silence" },
  { value: "1", label: "Standard" },
  { value: "2", label: "Strong" },
  { value: "3", label: "Turbo" },
];

export const x10WaterOptions = [
  { value: "1", label: "Low" },
  { value: "2", label: "Medium" },
  { value: "3", label: "High" },
];

export const x10DayOptions = [
  { index: 0, label: "Mon" },
  { index: 1, label: "Tue" },
  { index: 2, label: "Wed" },
  { index: 3, label: "Thu" },
  { index: 4, label: "Fri" },
  { index: 5, label: "Sat" },
  { index: 6, label: "Sun" },
];

const x10WeeklyTaskIds = [12, 13, 14, 17, 15, 16, 11];
const x10RobotDayMaskIndexByHcDay = [1, 2, 3, 4, 5, 6, 0];

export function parseSegmentList(value) {
  if (Array.isArray(value)) return value.map((item) => Number(item)).filter(Boolean);
  return String(value || "").split(",").map((item) => Number(item.trim())).filter(Boolean);
}

export function dayMaskFor(index) {
  const chars = ["0", "0", "0", "0", "0", "0", "0"];
  const robotIndex = x10RobotDayMaskIndexByHcDay[index] ?? index;
  chars[robotIndex] = "1";
  return chars.join("");
}

export function x10WeeklyDraftFromState(state) {
  const entries = Array.isArray(state?.scheduler_entries) ? state.scheduler_entries : [];
  return x10DayOptions.map((day) => {
    const taskId = x10WeeklyTaskIds[day.index];
    const entry = entries.find((item) => Number(item.task_id) === taskId);
    return {
      day_index: day.index,
      task_id: taskId,
      enabled: String(entry?.enabled ?? "0") === "1",
      start_time: entry?.time || "06:00",
      days: dayMaskFor(day.index),
      map_id: Number(entry?.map_id ?? state?.map?.current_id ?? 3),
      mode: textValue(entry?.clean_mode ?? entry?.flag ?? state?.clean_mode ?? 2),
      suction: textValue(entry?.suction ?? state?.suction ?? 3),
      water_level: textValue(entry?.water_level ?? entry?.clean_param ?? state?.water_level ?? 2),
      segments: parseSegmentList(entry?.segments),
    };
  });
}

export function normalizeWeeklySchedules(rows = []) {
  return rows.map((item) => ({
    day_index: Number(item.day_index),
    task_id: Number(item.task_id),
    enabled: Boolean(item.enabled),
    start_time: item.start_time || "06:00",
    map_id: Number(item.map_id || 3),
    mode: String(item.mode ?? "2"),
    suction: String(item.suction ?? "3"),
    water_level: String(item.water_level ?? "2"),
    segments: parseSegmentList(item.segments).sort((a, b) => a - b),
  })).sort((a, b) => a.day_index - b.day_index);
}

export function weeklyScheduleSignature(rows = []) {
  return JSON.stringify(normalizeWeeklySchedules(rows));
}
