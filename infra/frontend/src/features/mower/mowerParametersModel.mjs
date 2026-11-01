export const PARAMETER_GROUPS = [
  { title: "Azonosítás", fields: ["parameters_version", "robot_id", "blade_enabled"] },
  { title: "Geometria és érzékelők", fields: ["wheel_track_mm", "body_radius_mm", "wheel_circumference_mm", "antenna_body_mm", "imu_mount_q_ppm"] },
  { title: "Motorok és kés", fields: ["wheel_motor_pole_pairs", "wheel_gear_ratio_milli", "wheel_direction", "blade_direction", "blade_pole_pairs", "wheel_erpm_limit", "blade_erpm_limit", "blade_rpm_limit"] },
  { title: "Fékezés és biztonsági határok", fields: ["wheel_brake_ma", "stop_deceleration_mm_s2", "stop_test_max_ms", "max_slope_mdeg", "tilt_limit_mdeg"] },
  { title: "Mozgás és navigáció", fields: ["max_linear_mm_s", "max_yaw_mdeg_s", "accel_mm_s2", "yaw_accel_mdeg_s2", "gnss_hacc_limit_mm", "heading_accuracy_limit_mdeg"] },
];

export const FIELD_LABELS = {
  parameters_version: "Adatverzió", robot_id: "Paramétercsomag robotazonosítója", blade_enabled: "Kés engedélyezése a draftban",
  wheel_track_mm: "Nyomtáv", body_radius_mm: "Test sugara", wheel_circumference_mm: "Gördülési kerületek",
  antenna_body_mm: "Antenna helyzete a robothoz képest", imu_mount_q_ppm: "IMU beépítési kvaternió",
  wheel_motor_pole_pairs: "Kerékmotorok póluspárjai", wheel_gear_ratio_milli: "Kerékáttételek (ezredarány)",
  wheel_direction: "Kerékmotorok iránya", blade_direction: "Késmotor iránya", blade_pole_pairs: "Késmotor póluspárjai",
  wheel_erpm_limit: "Kerékmotorok elektromos fordulatlimitje", blade_erpm_limit: "Kés elektromos fordulatlimitje",
  blade_rpm_limit: "Kés mechanikai fordulatlimitje", wheel_brake_ma: "Kerékfékezési áramok",
  stop_deceleration_mm_s2: "Stop lassulása (mérést igényel)", stop_test_max_ms: "Stop teszt felső időhatára (mérést igényel)",
  max_slope_mdeg: "Megengedett lejtés", tilt_limit_mdeg: "Dőlési határ", max_linear_mm_s: "Maximális haladási sebesség",
  max_yaw_mdeg_s: "Maximális fordulási sebesség", accel_mm_s2: "Haladási gyorsulás", yaw_accel_mdeg_s2: "Fordulási gyorsulás",
  gnss_hacc_limit_mm: "GNSS vízszintes pontossági határ", heading_accuracy_limit_mdeg: "Iránybecslés pontossági határa",
};

export function fieldUnit(name) {
  for (const unit of ["mm_s2", "mdeg_s2", "mm_s", "mdeg_s", "mdeg", "mm", "ma", "ms", "ppm", "erpm", "rpm"]) {
    if (name.endsWith(`_${unit}`) || name.includes(`_${unit}_`)) return ({ mm_s2: "mm/s²", mdeg_s2: "millifok/s²", mm_s: "mm/s", mdeg_s: "millifok/s", mdeg: "millifok", ma: "mA" })[unit] || unit;
  }
  return "";
}

export function canonicalDraftText(parameters) {
  return JSON.stringify(Object.fromEntries(Object.keys(parameters).sort().map((key) => [key, parameters[key]])));
}

export function parameterChanges(base, parameters) {
  if (!base || !parameters) return [];
  return Object.keys(parameters).filter((field) => JSON.stringify(base[field]) !== JSON.stringify(parameters[field]))
    .map((field) => ({ field, before: base[field], after: parameters[field] }));
}

export function usableCachedForm(cached, schema) {
  return !!(cached && typeof cached.key === "string" && /^[A-Za-z0-9_-]{0,32}$/.test(cached.key)
    && Number.isInteger(cached.revision) && cached.revision >= 0 && cached.revision <= 0xffffffff
    && cached.base && cached.form && Object.keys(cached.form).sort().join() === Object.keys(schema.properties).sort().join()
    && Object.entries(schema.properties).every(([name, spec]) => spec.type === "array"
      ? Array.isArray(cached.form[name]) && cached.form[name].length === spec.minItems && cached.form[name].every((item) => typeof item === "string" && item.length <= 32)
      : typeof cached.form[name] === "string" && cached.form[name].length <= 32));
}

export function parametersToForm(parameters, schema) {
  return Object.fromEntries(Object.entries(schema.properties).map(([name, spec]) => {
    const value = parameters[name];
    if (spec.type === "array") return [name, Array.from({ length: spec.minItems }, (_, index) => value?.[index] == null ? "" : String(value[index]))];
    return [name, value == null ? "" : String(value)];
  }));
}

export function formToParameters(form, schema) {
  const parameters = {}, errors = [];
  function number(raw, field) {
    if (raw === "") return null;
    if (typeof raw !== "string" || !/^-?\d+$/.test(raw) || !Number.isSafeInteger(Number(raw))) {
      errors.push({ field, message: "Egész szám szükséges; tizedes és exponenciális alak nem engedélyezett." });
      return null;
    }
    return Number(raw);
  }
  for (const [name, spec] of Object.entries(schema.properties)) {
    const raw = form[name];
    if (spec.type === "array") {
      if (!Array.isArray(raw) || raw.length !== spec.minItems) {
        errors.push({ field: name, message: `Pontosan ${spec.minItems} elem szükséges.` }); parameters[name] = null;
      } else parameters[name] = raw.every((item) => item === "") ? null : raw.map((item, index) => number(item, `${name}[${index}]`));
    } else if (spec.type === "integer") parameters[name] = number(raw, name);
    else if (spec.type === "boolean") {
      if (!["", "true", "false"].includes(raw)) errors.push({ field: name, message: "Ismeretlen / igen / nem érték szükséges." });
      parameters[name] = raw === "" ? null : raw === "true";
    } else {
      if (typeof raw !== "string") errors.push({ field: name, message: "Szöveges érték szükséges." });
      parameters[name] = raw === "" ? null : raw;
    }
  }
  return { parameters, errors };
}

export function savedDraftMatches(result, attempt) {
  return result?.source === "HC_DRAFT" && result.apply_available === false && result.request_id === attempt.request_id
    && result.rover_key === attempt.key && result.draft_revision === attempt.expected_revision + 1
    && result.parameters && canonicalDraftText(result.parameters) === canonicalDraftText(attempt.parameters);
}
