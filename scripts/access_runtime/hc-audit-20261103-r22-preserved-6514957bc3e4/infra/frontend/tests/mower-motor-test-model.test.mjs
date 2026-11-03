import assert from "node:assert/strict";
import { test } from "node:test";
import { validApplyCorrelation, confirmedApplyOutcome } from "../src/features/mower/mowerMotorTestModel.mjs";
const pending = { request_id:"old-apply",esp_boot:"1111111111111111",stm_boot:"2222222222222222",expected_revision:2,parameters_crc:"27384620" };
function cancelled() { return {request_id:"old-apply",result:"CANCELLED",code:"BOOT_CHANGED",snapshot:{
  connection:{status:"LIVE"},freshness:{fresh:true},identity:{mode:"MOTOR_TEST",esp_boot:"3333333333333333",stm_boot:"4444444444444444",runtime_parameters:true},
  state:{control_epoch:3,state:"DISARMED",armed:false,stopped:true,manual_lease_id:null},
  parameters:{esp_boot:"3333333333333333",stm_boot:"4444444444444444",control_epoch:3,storage:"ACTIVE",applied:true,busy:false,available:true,source_valid:true,source_age_ms:100,parameters:{},can_apply:true,revision:1,request_id:"previous-apply",parameters_crc:"27384620"}}}; }
test("old-boot Apply only resolves as cancelled after fresh settled prior ACTIVE, preserving its distinct outcome",()=>{
  assert.equal(validApplyCorrelation(pending),true); assert.equal(confirmedApplyOutcome(cancelled(),pending),true);
  for(const update of [{busy:true},{storage:"PENDING"},{storage:"FAULT"},{source_age_ms:1501},{applied:false},{can_apply:false},{revision:2}]){
    const result=cancelled(); Object.assign(result.snapshot.parameters,update); assert.equal(confirmedApplyOutcome(result,pending),false);
  }
  const same=cancelled(); same.snapshot.identity.esp_boot=pending.esp_boot; same.snapshot.identity.stm_boot=pending.stm_boot;
  same.snapshot.parameters.esp_boot=pending.esp_boot; same.snapshot.parameters.stm_boot=pending.stm_boot;
  assert.equal(confirmedApplyOutcome(same,pending),false);
  assert.equal(confirmedApplyOutcome({...cancelled(),request_id:"other"},pending),false);
});
test("restored APPLIED must still match exact request/revision/CRC, malformed pending never unlocks",()=>{
  const result=cancelled(); result.result="APPLIED"; Object.assign(result.snapshot.parameters,{request_id:pending.request_id,revision:2});
  assert.equal(confirmedApplyOutcome(result,pending),true);
  result.snapshot.parameters.parameters_crc="11111111"; assert.equal(confirmedApplyOutcome(result,pending),false);
  for(const corrupt of [{...pending,expected_revision:true},{...pending,esp_boot:"bad"},{...pending,force:true}]) assert.equal(validApplyCorrelation(corrupt),false);
});
