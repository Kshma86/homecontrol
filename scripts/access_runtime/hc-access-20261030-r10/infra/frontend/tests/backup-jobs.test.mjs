import test from "node:test";
import assert from "node:assert/strict";
import { backupProgress } from "../src/features/backup/backupJobState.mjs";
const request = {run_id:"a",kind:"local",requestedAt:0};
test("accepted request remains queued until its own job completes", () => {
  assert.equal(backupProgress(request, [{run_id:"b",state:"completed"}], 1000).pending,true);
});
test("queue delay does not turn into a successful backup", () => {
  const result=backupProgress(request, [], 90000);
  assert.equal(result.pending,true); assert.match(result.message,/waiting/); assert.equal(result.success,undefined);
});
test("running job has no invented archive", () => {
  const result=backupProgress(request,[{run_id:"a",state:"running"}]);
  assert.equal(result.pending,true);assert.equal(result.archive,undefined);
});
test("only completed matching job reports success and selects its artifact", () => {
  const result=backupProgress(request,[{run_id:"a",state:"completed",archive:{name:"verified.tar.gz"}}]);
  assert.equal(result.success,true);assert.equal(result.pending,false);assert.equal(result.archive,"verified.tar.gz");
});
test("failed remote target does not become success because a local archive exists", () => {
  const result=backupProgress(request,[{run_id:"a",state:"failed",archive:{name:"verified.tar.gz"}}]);
  assert.equal(result.success,false);assert.equal(result.pending,false);assert.match(result.message,/failed/);
});
test("interrupted job is explicit", () => {
  const result=backupProgress({...request,kind:"weekly"},[{run_id:"a",state:"interrupted"}]);
  assert.equal(result.success,false);assert.match(result.message,/Full AI backup interrupted/);
});
