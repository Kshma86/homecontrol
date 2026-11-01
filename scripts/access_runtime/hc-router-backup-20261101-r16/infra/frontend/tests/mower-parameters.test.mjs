import assert from "node:assert/strict";
import { test } from "node:test";
import { PARAMETER_GROUPS, canonicalDraftText, fieldUnit, formToParameters, parameterChanges, parametersToForm, savedDraftMatches, usableCachedForm } from "../src/features/mower/mowerParametersModel.mjs";

const schema = { properties: {
  parameters_version: { type: "integer", const: 1 }, robot_id: { type: "string" }, blade_enabled: { type: "boolean" },
  wheel_track_mm: { type: "integer", minimum: 100, maximum: 1500 }, wheel_direction: { type: "array", minItems: 2, items: { type: "integer", enum: [-1, 1] } },
} };
const blank = { parameters_version: 1, robot_id: null, blade_enabled: null, wheel_track_mm: null, wheel_direction: null };

test("null values remain unknown including blade enablement and array elements", () => {
  const form = parametersToForm(blank, schema);
  assert.deepEqual(form.wheel_direction, ["", ""]);
  assert.equal(form.blade_enabled, "");
  assert.deepEqual(formToParameters(form, schema), { parameters: blank, errors: [] });
  form.wheel_direction = ["", "-1"];
  assert.deepEqual(formToParameters(form, schema).parameters.wheel_direction, [null, -1]);
});

test("interactive numeric text does not silently coerce decimal, exponent, NaN or bools", () => {
  for (const raw of ["500.0", "1e2", "NaN", "Infinity", "true", "1.2", true, "9007199254740992"]) {
    const result = formToParameters({ ...parametersToForm(blank, schema), wheel_track_mm: raw }, schema);
    assert.equal(result.errors[0].field, "wheel_track_mm");
  }
});

test("draft form roundtrip preserves booleans, directions and zero", () => {
  const parameters = { ...blank, robot_id: "test_only", blade_enabled: false, wheel_track_mm: 500, wheel_direction: [1, -1] };
  assert.deepEqual(formToParameters(parametersToForm(parameters, schema), schema).parameters, parameters);
  assert.equal(formToParameters({ ...parametersToForm(blank, schema), wheel_track_mm: "0" }, schema).parameters.wheel_track_mm, 0);
});

test("canonical comparison ignores object order but not null vs zero or array order", () => {
  assert.equal(canonicalDraftText(blank), canonicalDraftText(Object.fromEntries(Object.entries(blank).reverse())));
  assert.notEqual(canonicalDraftText(blank), canonicalDraftText({ ...blank, wheel_track_mm: 0 }));
  assert.notEqual(canonicalDraftText({ a: [1, -1] }), canonicalDraftText({ a: [-1, 1] }));
});

test("all 27 reference fields occur exactly once in editor groups", () => {
  const fields = PARAMETER_GROUPS.flatMap((group) => group.fields);
  assert.equal(fields.length, 27);
  assert.equal(new Set(fields).size, 27);
  assert.ok(!fields.includes("commissioned"));
  assert.ok(!fields.includes("profile_crc"));
});

test("saved HC acknowledgement correlates alias, id, revision and exact attempted parameters", () => {
  const attempt = { key: "hc-test", request_id: "save-1", expected_revision: 3, parameters: blank };
  const result = { source: "HC_DRAFT", apply_available: false, rover_key: "hc-test", request_id: "save-1", draft_revision: 4, parameters: blank };
  assert.equal(savedDraftMatches(result, attempt), true);
  for (const update of [{ source: "ROVER_ACTIVE" }, { rover_key: "other" }, { request_id: "other" }, { draft_revision: 5 },
    { apply_available: true }, { parameters: { ...blank, blade_enabled: false } }]) {
    assert.equal(savedDraftMatches({ ...result, ...update }, attempt), false);
  }
});

test("units distinguish physical and scaled angular values", () => {
  assert.equal(fieldUnit("max_linear_mm_s"), "mm/s");
  assert.equal(fieldUnit("yaw_accel_mdeg_s2"), "millifok/s²");
  assert.equal(fieldUnit("wheel_brake_ma"), "mA");
  assert.equal(fieldUnit("imu_mount_q_ppm"), "ppm");
});

test("draft differences preserve unknown vs false and measurement changes", () => {
  assert.deepEqual(parameterChanges(blank, { ...blank, blade_enabled: false, wheel_track_mm: 500 }),
    [{ field: "blade_enabled", before: null, after: false }, { field: "wheel_track_mm", before: null, after: 500 }]);
});

test("corrupt cached form cannot crash array rendering or imply a saved revision", () => {
  const cached = { key: "hc-test", revision: 0, base: blank, form: parametersToForm(blank, schema) };
  assert.equal(usableCachedForm(cached, schema), true);
  assert.equal(usableCachedForm({ ...cached, revision: true }, schema), false);
  assert.equal(usableCachedForm({ ...cached, form: { ...cached.form, wheel_direction: "wrong" } }, schema), false);
  assert.equal(usableCachedForm({ ...cached, form: { ...cached.form, wheel_direction: [0, 1] } }, schema), false);
});
