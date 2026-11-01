import test from "node:test";
import assert from "node:assert/strict";
import { aiPowerStatus } from "../src/features/ai/aiPowerState.mjs";

test("missing or unknown lock state never appears clear", () => {
  for (const guard of [{}, {backup_running:null}, {backup_running:false,guard_known:false}]) {
    const state=aiPowerStatus(guard);assert.equal(state.label,"Unknown");assert.equal(state.warn,true);
  }
});
test("a running backup is visible", () => {
  assert.equal(aiPowerStatus({backup_running:true}).label,"Backup running");
});
test("deferred shutdown has no invented countdown", () => {
  const state=aiPowerStatus({backup_running:false,deferred_shutdown:{phase:"shutdown"}});
  assert.equal(state.label,"Shutdown queued");assert.equal(state.remainingSec,0);
});
test("countdown comes from the current server intent", () => {
  const state=aiPowerStatus({backup_running:false,pending_power_off:{due_at_epoch:105}},100000);
  assert.equal(state.remainingSec,5);assert.equal(state.label,"Power off scheduled");
});
test("cancelled intent clears the countdown without a local fallback", () => {
  const state=aiPowerStatus({backup_running:false,pending_power_off:null},100000);
  assert.equal(state.remainingSec,0);assert.equal(state.label,"Clear");
});
