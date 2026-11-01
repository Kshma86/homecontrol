import assert from "node:assert/strict";
import { test } from "node:test";
import { fileURLToPath } from "node:url";
import { dirname } from "node:path";
import Module from "node:module";
import { build } from "esbuild";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { validUpdateSession, validSessionAttempt, validSessionIntent, updateView, validActionIntent, validActionResult } from "../src/features/mower/mowerUpdateModel.mjs";

const KEY = "hc.mower.v3.update.pending-create.v1", jobId = "2".repeat(32), updateId = "3".repeat(32);
const ACTION_KEY = "hc.mower.v3.update.pending-action.v1";
const intent = { jobId, requestId: "1".repeat(32) };
const identity = { v:3,contract:"3.1.0",esp_boot:"0123456789ABCDEF",profile_crc:"AABBCCDD",stm_remote_update:true,
  update_service_abi:2,stm_flash_layout:"H743_1M_QSPI2",stm_image_max_bytes:524288,esp_ota_max_bytes:1048576,
  stm_confirmed_slot:null,stm_inactive_slot:null,update_locked:false };
const idle = { v:3,update_id:null,target:null,locked:false,phase:"IDLE",error:"NONE",detail:"NONE",esp_boot:identity.esp_boot,
  stm_service_boot:null,source:"NONE",source_age_ms:null,source_valid:false,image_bytes:0,http_received_bytes:0,stm_written_bytes:0,
  image_sha256:null,fw_id:null,confirmed_slot:null,inactive_slot:null,candidate_slot:null,bootloader_fw:"loader",last_phase_ms:10,
  can_active:null,outputs_inhibited:null,stop_evidence:"UNKNOWN",stop_evidence_age_ms:null,can_retry:false,can_finish:false };
const ready = { ...idle,update_id:updateId,target:"STM",locked:true,phase:"READY",source:"STM_LOADER",source_valid:true,
  source_age_ms:10,stm_service_boot:"1122334455667788",can_active:false,outputs_inhibited:true };
const attempt = { request_id:intent.requestId,hc_job_id:jobId,state:"ADMITTED",active:true,update_id:updateId,esp_boot:identity.esp_boot,
  profile_crc:identity.profile_crc,revision:2,code:"ADMITTED",persisted:true,created_at:"2026-10-10T16:00:00Z",updated_at:"2026-10-10T16:00:00Z",
  progress_path:`/api/v3/update/${updateId}` };
const initial = { ok:true,scope:"HC_NATIVE_SESSION",configured:true,attempt:null,identity,observation:idle,connection:{status:"IDLE"},
  bound:false,can_create:true,ordinary_blocked:false,ready:false,installation_confirmed:false,
  freshness:{fresh:false,effective_age_ms:null,timeout_ms:2000},upload_available:false,abort_available:false,finish_available:false,
  hardware_qualified:false,normal_mode_verified:false };
const admitted = { ...initial,attempt,identity:null,observation:null,can_create:false,ordinary_blocked:true,connection:{status:"ADMITTED"} };
const observed = { ...admitted,identity:{...identity,update_locked:true},observation:ready,connection:{status:"LIVE"},bound:true,ready:true,
  freshness:{fresh:true,effective_age_ms:10,timeout_ms:2000} };
const unknown = { ...admitted,attempt:{...attempt,state:"UNKNOWN",update_id:null,progress_path:null,code:"REPLY_LOST"},connection:{status:"UNBOUND"} };

test("native session descriptors require a retained admission and exact current binding", () => {
  assert.equal(validSessionIntent(intent), true); assert.equal(validSessionAttempt(attempt, intent), true);
  assert.equal(validUpdateSession(initial), true); assert.equal(validUpdateSession(admitted, intent), true); assert.equal(validUpdateSession(observed, intent), true);
  for (const change of [{ state:"READY" },{ active:false },{ revision:1 },{ update_id:"0".repeat(32) },{ hc_job_id:"other" },
    { request_id:"other" },{ progress_path:"https://evil.test" },{ persisted:false },{ esp_boot:"a".repeat(16) }]) assert.equal(validSessionAttempt({...attempt,...change}, intent), false);
  for (const change of [{upload_available:true},{abort_available:true},{finish_available:true},{hardware_qualified:true},{normal_mode_verified:true},
    {ordinary_blocked:false},{configured:false},{connection:{status:"BOOT_CHANGED"}},{connection:{status:"AUTH_FAILED"}},
    {attempt:{...attempt,update_id:"4".repeat(32),progress_path:`/api/v3/update/${"4".repeat(32)}`}},
    {identity:{...identity,esp_boot:"5".repeat(16)}},{identity:{...identity,profile_crc:"11223344"}},
    {observation:{...ready,candidate_slot:"NONE"}},{observation:{...ready,stm_written_bytes:1}}]) assert.equal(validUpdateSession({...observed,...change}), false);
});

test("unbound/stale/trial/null source cannot prove READY or committed installation", () => {
  assert.equal(validUpdateSession(unknown), true);
  for (const change of [{bound:false},{freshness:{fresh:false,effective_age_ms:2001,timeout_ms:2000}},
    {observation:{...ready,source:"STM_TRIAL"}},{observation:{...ready,can_active:null}},{observation:{...ready,outputs_inhibited:null}}])
    assert.equal(validUpdateSession({...observed,...change}), false);
  assert.equal(validUpdateSession({...observed,ready:false,observation:{...ready,source:"STM_TRIAL",phase:"TRIAL"},installation_confirmed:true}), false);
  const complete = {...observed,ready:false,observation:{...ready,phase:"COMPLETE",image_bytes:1536,http_received_bytes:1536,stm_written_bytes:1536,
    image_sha256:"a".repeat(64),fw_id:"reviewed"},installation_confirmed:true};
  assert.equal(validUpdateSession(complete), true);
  assert.equal(updateView(complete,100,2101).installed, false);
  assert.equal(updateView(observed,100,2101).ready, false);
  assert.equal(updateView(observed,100,101,"Disconnected").fresh, false);
  assert.equal(updateView(initial,100,2101).canCreate, false);
  assert.equal(updateView(initial,100,101).canCreate, true);
});

async function harness({ initialIntent=null, authenticated=true, configured=true, postMode="ok", lookupMode="found", storageFails=false,
  actions=false, actionMode="ok", restoreAction=null, actionLookupMode="found" } = {}) {
  let cursor=0, needsRender=false, value, time=0, auth=authenticated, config=configured, posted=false, readMode="ok";
  const slots=[],effects=[],calls=[],timers=new Map(),storage=new Map(initialIntent===null?[]:[[KEY,initialIntent]]);
  let timerId=0;
  let randomCounter=0x11, phase="READY", operation=null, exit=null;
  if (restoreAction) storage.set(ACTION_KEY,typeof restoreAction === "string" ? restoreAction : JSON.stringify(restoreAction));
  const actionReply = (actionIntent) => ({ok:true,scope:"HC_UPDATE_ACTION",found:true,exit:null,operation:{request_id:actionIntent.requestId,
    session_request_id:actionIntent.sessionId,action:actionIntent.action,state:actionMode==="lost"?"UNKNOWN":"ADMITTED",code:"ADMITTED",
    service_boot:ready.stm_service_boot,persisted:true,created_at:attempt.created_at,updated_at:attempt.updated_at}});
  const hooks={
    useState(initial) { const index=cursor++; if(!slots[index]) slots[index]={value:initial}; return [slots[index].value,(next)=>{slots[index].value=typeof next==="function"?next(slots[index].value):next;needsRender=true;}]; },
    useRef(initial) { const index=cursor++; if(!slots[index]) slots[index]={current:initial}; return slots[index]; },
    useEffect(callback,deps) { const index=cursor++,previous=slots[index]; if(!previous||deps.some((next,i)=>next!==previous.deps[i])) effects.push(()=>{previous?.cleanup?.();slots[index]={deps,cleanup:callback()};}); },
  };
  const originals={window:globalThis.window,fetch:globalThis.fetch,performance:globalThis.performance,hooks:globalThis.__updateHooks};
  globalThis.__updateHooks=hooks;globalThis.performance={now:()=>time};
  globalThis.window={crypto:{getRandomValues:(bytes)=>bytes.fill(randomCounter++)},
    setTimeout:()=>++timerId,clearTimeout:()=>{},setInterval(callback,ms){const id=++timerId;timers.set(id,{callback,ms});return id;},clearInterval:(id)=>timers.delete(id),
    sessionStorage:{getItem:(key)=>storage.get(key)??null,setItem(key,raw){if(storageFails)throw new Error("Storage denied");storage.set(key,raw);},removeItem:(key)=>storage.delete(key)}};
  globalThis.fetch=async(path,options={})=>{
    calls.push({path,method:options.method||"GET",options});
    if (path.includes("/operations/requests/")) {
      const cached=operation || actionReply(restoreAction);
      return {ok:true,status:200,json:async()=>actionLookupMode==="missing"?{ok:true,scope:"HC_UPDATE_ACTION",found:false}
        :actionLookupMode==="mismatch"?{...cached,operation:{...cached.operation,session_request_id:"other"}}:cached};
    }
    if (options.method==="POST" && path.includes("/sessions/requests/")) {
      assert.ok(storage.has(ACTION_KEY));
      const correlation=JSON.parse(storage.get(ACTION_KEY)); assert.equal(JSON.parse(options.body).request_id,correlation.requestId);
      if(correlation.action==="VERIFY_EXIT") {
        exit={ok:true,scope:"HC_UPDATE_ACTION",found:true,operation:null,exit:{request_id:correlation.requestId,session_request_id:correlation.sessionId,
          persisted:true,created_at:attempt.created_at,proof:{esp_boot:identity.esp_boot,stm_boot:"9988776655443322",profile_crc:identity.profile_crc,
          control_epoch:1,state:"DISARMED",store:"EMPTY",fault_mask:0,zero_targets_authority:"NATIVE_IDLE_RESTART_BARRIER"}}};
        operation=exit;return{ok:true,status:200,json:async()=>exit};
      }
      operation=actionReply(correlation);
      if(actionMode==="lost")throw new Error("Lost action response");
      return{ok:true,status:200,json:async()=>actionMode==="malformed"?{...operation,operation:{...operation.operation,action:"OTHER"}}:operation};
    }
    if(options.method==="POST"){
      posted=true; assert.ok(storage.has(KEY),"Intent must precede create POST");
      if(postMode==="lost")throw new Error("Lost create response");
      if(postMode==="reject")return {ok:false,status:409,json:async()=>({ok:false,mutation_sent:false,code:"PROFILE_MISMATCH",error:"Profile"})};
      return {ok:true,status:200,json:async()=>postMode==="malformed"?{...admitted,attempt:{...attempt,hc_job_id:"6".repeat(32)}}:admitted};
    }
    const data = readMode==="lost"?{...admitted,connection:{status:"UNREACHABLE"}}:path.includes("/requests/")
      ?lookupMode==="missing"?{...admitted,attempt:null,ordinary_blocked:false,found:false}:lookupMode==="mismatch"?{...admitted,attempt:{...attempt,hc_job_id:"6".repeat(32)},found:true}
        :{...(postMode==="lost"?unknown:observed),found:true}
      :posted?observed:initial;
    const enhanced = exit ? initial : actions && data===observed ? {...observed,ready:phase==="READY",operations:operation?.operation?[operation.operation]:[],
      observation:{...ready,phase,can_finish:phase==="COMPLETE"},upload_available:phase==="READY"&&!operation,
      abort_available:phase==="READY"&&operation?.operation?.action!=="ABORT",finish_available:phase==="COMPLETE"&&operation?.operation?.action!=="FINISH",
      exit_check_available:operation?.operation?.action==="FINISH"} : data;
    return {ok:true,status:200,json:async()=>enhanced};
  };
  const bundled=await build({entryPoints:[fileURLToPath(new URL("../src/features/mower/useMowerUpdateSession.js",import.meta.url))],bundle:true,write:false,platform:"node",format:"cjs",
    plugins:[{name:"update-hooks",setup(builder){builder.onResolve({filter:/^react$/},()=>({path:"hooks",namespace:"mock"}));builder.onLoad({filter:/.*/,namespace:"mock"},()=>({contents:"export const {useState,useRef,useEffect}=globalThis.__updateHooks;",loader:"js"}));}}]});
  const compiled=new Module("update-hooks");compiled._compile(bundled.outputFiles[0].text,"update-hooks.cjs");
  function render(){do{needsRender=false;cursor=0;value=compiled.exports.default({authenticated:auth,configured:config});while(effects.length)effects.shift()();}while(needsRender);}
  async function settle(){for(let i=0;i<20;i++){await Promise.resolve();if(needsRender)render();}}
  render();await settle();
  return {calls,storage,get value(){return value;},async act(callback){await callback(value);await settle();},
    async tick(ms){time+=ms;for(const timer of [...timers.values()])if(ms>=timer.ms)timer.callback();await settle();},
    async setAuth(next){auth=next;render();await settle();},setReadMode(next){readMode=next;},setPhase(next){phase=next;},
    close(){for(const slot of slots)slot?.cleanup?.();globalThis.window=originals.window;globalThis.fetch=originals.fetch;globalThis.performance=originals.performance;globalThis.__updateHooks=originals.hooks;}};
}

test("session hook sends only an explicit confirmed create, blocks controls, and polls only GET at 2 Hz", async()=>{
  const runner=await harness();
  try{
    assert.deepEqual(runner.calls.map((call)=>call.method),["GET"]);assert.equal(runner.value.canCreate,true);
    await runner.act(async(value)=>{const first=value.create(jobId);await value.create(jobId);await first;});
    assert.equal(runner.calls.filter((call)=>call.method==="POST").length,1);assert.equal(runner.value.blocked,true);
    assert.equal(runner.value.pending,null);assert.equal(runner.value.ready,false);
    assert.deepEqual(JSON.parse(runner.calls[1].options.body),{request_id:intent.requestId,confirm_runtime_discard:true});
    await runner.tick(500);assert.equal(runner.value.ready,true);assert.equal(runner.calls.at(-1).method,"GET");
    assert.ok(runner.calls.every((call)=>!call.path.includes("/image")&&!call.path.includes("/abort")&&!call.path.includes("/finish")));
  }finally{runner.close();}
});

test("lost/malformed create replies never resend; retained UNKNOWN still blocks normal controls",async()=>{
  for(const postMode of ["lost","malformed"]){
    const runner=await harness({postMode});
    try{
      await runner.act((value)=>value.create(jobId));assert.ok(runner.value.pending);assert.equal(runner.value.blocked,true);
      await runner.act((value)=>value.create(jobId));assert.equal(runner.calls.filter((call)=>call.method==="POST").length,1);
      await runner.act((value)=>value.refresh());assert.equal(runner.value.pending,null);assert.equal(runner.value.blocked,true);
      assert.equal(runner.calls.at(-1).method,"GET");assert.equal(runner.calls.filter((call)=>call.method==="POST").length,1);
      if(postMode==="lost"){assert.equal(runner.value.result.attempt.update_id,null);assert.equal(runner.value.ready,false);}
    }finally{runner.close();}
  }
});

test("restore is GET-only; absent/mismatched record and corrupted correlation remain blocked",async()=>{
  for(const lookupMode of ["found","missing","mismatch"]){
    const runner=await harness({initialIntent:JSON.stringify(intent),lookupMode});
    try{
      assert.equal(runner.calls.length,1);assert.match(runner.calls[0].path,/\/requests\//);
      assert.equal(runner.value.blocked,true);
      if(lookupMode!=="found"){assert.ok(runner.value.pending);await runner.act((value)=>value.create(jobId));await runner.tick(500);assert.ok(runner.value.pending);}
      assert.equal(runner.calls.filter((call)=>call.method==="POST").length,0);
    }finally{runner.close();}
  }
  const broken=await harness({initialIntent:"{broken"});
  try{await broken.act((value)=>value.create(jobId));assert.equal(broken.value.pending.invalid,true);assert.equal(broken.calls.length,0);}finally{broken.close();}
});

test("unauthenticated, unconfigured or unavailable correlation storage never starts a native create",async()=>{
  for(const options of [{authenticated:false},{configured:false},{storageFails:true}]){
    const runner=await harness(options);
    try{await runner.act((value)=>value.create(jobId));assert.equal(runner.calls.filter((call)=>call.method==="POST").length,0);}finally{runner.close();}
  }
  const rejected=await harness({postMode:"reject"});
  try{await rejected.act((value)=>value.create(jobId));assert.equal(rejected.value.pending,null);assert.equal(rejected.storage.has(KEY),false);assert.ok(rejected.value.error);}
  finally{rejected.close();}
});

test("lost current observation preserves historical progress without READY/install permission",async()=>{
  const runner=await harness();
  try{
    await runner.act((value)=>value.create(jobId));await runner.tick(500);assert.equal(runner.value.ready,true);
    runner.setReadMode("lost");await runner.tick(2500);
    assert.equal(runner.value.result.observation,null);assert.equal(runner.value.lastObservation.phase,"READY");
    assert.equal(runner.value.ready,false);assert.equal(runner.value.installed,false);assert.equal(runner.value.blocked,true);
    assert.ok(runner.value.lastAge>2000);
  }finally{runner.close();}
});

test("session UI separates admission, stale evidence and independently gated explicit update actions",async()=>{
  const filename=fileURLToPath(new URL("./mower-update-ui-test.cjs",import.meta.url));
  const bundled=await build({entryPoints:[fileURLToPath(new URL("../src/features/mower/MowerFirmwareSession.jsx",import.meta.url))],bundle:true,write:false,platform:"node",format:"cjs",external:["react","lucide-react"]});
  const compiled=new Module(filename);compiled.paths=Module._nodeModulePaths(dirname(filename));compiled._compile(bundled.outputFiles[0].text,filename);
  const html=renderToStaticMarkup(React.createElement(compiled.exports.default,{updates:{result:observed,blocked:true,busy:false,fresh:false,ready:false,installed:false,effectiveAge:3000,canRead:true},jobs:[]}));
  for(const text of ["runtime törléssel","checkpoint","nem telepítési siker","Elavult","Ismeretlen","Natív update_id","Üzemi vezérlés zárolva"])
    assert.ok(html.includes(text),text);
  assert.match(html,/<button[^>]*disabled=""[^>]*>.*?<span>RFU2-kép feltöltése — egyszer<\/span>/);
  assert.ok(html.includes("Normál visszatérés ellenőrzése"));
  assert.ok(!html.includes("loader READY állapota friss és igazolt"));
});

test("native action gates require fresh bound evidence, exact intent and immutable operation correlation",()=>{
  const enabled={...observed,operations:[],upload_available:true,abort_available:true,exit_check_available:false};
  assert.equal(validUpdateSession(enabled),true);
  assert.equal(updateView(enabled,100,2101).canUpload,false);
  assert.equal(validUpdateSession({...enabled,freshness:{fresh:false,effective_age_ms:2001,timeout_ms:2000}}),false);
  const correlation={action:"IMAGE",sessionId:intent.requestId,requestId:"action-1"};
  const op={request_id:correlation.requestId,session_request_id:correlation.sessionId,action:"IMAGE",state:"UNKNOWN",code:"REPLY_LOST",
    service_boot:ready.stm_service_boot,persisted:true,created_at:attempt.created_at,updated_at:attempt.updated_at};
  const result={ok:true,scope:"HC_UPDATE_ACTION",found:true,operation:op,exit:null};
  assert.equal(validActionIntent(correlation),true);assert.equal(validActionResult(result,correlation),true);
  assert.equal(validActionResult({...result,operation:{...op,session_request_id:"other"}},correlation),false);
  assert.equal(validUpdateSession({...enabled,operations:[op]}),false);
  assert.equal(validUpdateSession({...observed,operations:[op],exit_check_available:true}),false);
});

test("image is explicit single-send; lost/malformed action uses GET-only durable lookup",async()=>{
  for(const actionMode of ["ok","lost","malformed"]){
    const runner=await harness({actions:true,actionMode});
    try{
      await runner.act((value)=>value.create(jobId));await runner.tick(500);
      assert.equal(runner.value.canUpload,true);
      await runner.act(async(value)=>{const first=value.perform("IMAGE");await value.perform("IMAGE");await first;});
      assert.equal(runner.calls.filter((call)=>call.path.endsWith("/image")&&call.method==="POST").length,1);
      if(actionMode!=="ok")assert.ok(runner.value.pending);
      await runner.act((value)=>value.refresh());
      assert.equal(runner.value.pending,null);assert.equal(runner.value.canUpload,false);assert.equal(runner.value.blocked,true);
      await runner.act((value)=>value.perform("IMAGE"));
      assert.equal(runner.calls.filter((call)=>call.path.endsWith("/image")&&call.method==="POST").length,1);
    }finally{runner.close();}
  }
});

test("restored action uncertainty cannot resend on negative/mismatched GET or corrupt local intent",async()=>{
  const restoreAction={action:"IMAGE",sessionId:intent.requestId,requestId:"action-1"};
  for(const actionLookupMode of ["missing","mismatch"]){
    const runner=await harness({restoreAction,actionLookupMode,actions:true});
    try{assert.ok(runner.value.pending);assert.equal(runner.value.blocked,true);await runner.act((value)=>value.perform("IMAGE"));
      assert.equal(runner.calls.filter((call)=>call.method==="POST").length,0);}finally{runner.close();}
  }
  const broken=await harness({restoreAction:"{bad"});
  try{assert.equal(broken.value.blocked,true);await broken.act((value)=>value.perform("ABORT"));assert.equal(broken.calls.length,0);}finally{broken.close();}
});

test("FINISH does not unlock; separate explicit verified exit clears old control generation",async()=>{
  const runner=await harness({actions:true});
  try{
    await runner.act((value)=>value.create(jobId));runner.setPhase("COMPLETE");await runner.tick(500);
    assert.equal(runner.value.canFinish,true);await runner.act((value)=>value.perform("FINISH"));
    assert.equal(runner.value.blocked,true);assert.equal(runner.value.canVerifyExit,true);assert.equal(runner.value.exitRevision,null);
    await runner.act((value)=>value.perform("VERIFY_EXIT"));
    assert.equal(runner.value.blocked,false);assert.ok(runner.value.exitRevision);assert.ok(runner.value.lastAction.exit);
    assert.ok(!runner.calls.some((call)=>call.path.endsWith("/command")||call.path.endsWith("/activate")));
  }finally{runner.close();}
});
