import assert from "node:assert/strict";
import { test } from "node:test";
import { readFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import Module from "node:module";
import { build } from "esbuild";
const initial=JSON.parse(await readFile(new URL("./fixtures/rover-motor-test.initial.json",import.meta.url),"utf8"));
const pending={request_id:"old-apply",esp_boot:"1111111111111111",stm_boot:"2222222222222222",expected_revision:2,parameters_crc:"27384620"};
const canonical=p=>JSON.stringify(p,Object.keys(p).sort());
async function harness(){
  let server=structuredClone(initial), revision=3, pendingState=false, confirmed=false, lost=false;

  const slots=[],effects=[],timers=new Map(),calls=[],storage=new Map(); let cursor=0,dirty=false,result,id=0;
  const original=Object.fromEntries(["window","sessionStorage","fetch","__configHooks"].map(key=>[key,globalThis[key]]));
  globalThis.__configHooks={useState(initial){const i=cursor++;if(!slots[i])slots[i]={value:initial};return[slots[i].value,value=>{slots[i].value=typeof value==="function"?value(slots[i].value):value;dirty=true;}];},useRef(initial){const i=cursor++;if(!slots[i])slots[i]={current:initial};return slots[i];},useEffect(callback,deps){const i=cursor++;if(!slots[i]||deps.some((v,j)=>!Object.is(v,slots[i].deps[j])))effects.push(()=>{slots[i]?.cleanup?.();slots[i]={deps,cleanup:callback()};});}};
  globalThis.window={setTimeout(fn,ms){const key=++id;timers.set(key,{fn,ms});return key;},clearTimeout(key){timers.delete(key);}};
  globalThis.sessionStorage={getItem:key=>storage.get(key)||null,setItem:(key,value)=>storage.set(key,value)};
  const snapshot={controls_disabled:false,connection:{status:"LIVE"},freshness:{fresh:true},identity:{mode:"MOTOR_TEST",esp_boot:"3333333333333333",stm_boot:"4444444444444444",runtime_parameters:true},state:{state:"DISARMED",stopped:true,armed:false,manual_lease_id:null,control_epoch:3},parameters:{storage:"ACTIVE",applied:true,busy:false,available:true,source_valid:true,source_age_ms:100,can_apply:true,revision:3,request_id:"previous",parameters_crc:"27384620",parameters:initial,esp_boot:"3333333333333333",stm_boot:"4444444444444444",control_epoch:3}};
  globalThis.fetch=async(path,options={})=>{calls.push({path,method:options.method||"GET",body:options.body});let payload,status=200;
    if(path.endsWith("/motor-test/config"))payload={ok:true,parameters:server,source:server?"rover_stored":"unavailable",canonical_rcp:server?canonical(server):null,validation:server?{valid:true,parameters_crc:"27384620"}:null,rover_status:{revision,parameters_crc:"27384620",can_apply:!pendingState,applied:!pendingState,storage:pendingState?"PENDING":"ACTIVE",code:pendingState?"CONFIG_RECOVERY_REQUIRED":"APPLIED"}};
    else if(path.endsWith("/motor-test/status"))payload={ok:true,snapshot:{...snapshot,parameters:{...snapshot.parameters,revision,can_apply:!pendingState}}};
    else if(path.includes("/parameters/drafts/"))payload={ok:true,draft_revision:9,parameters:initial};
    else if(path.endsWith("/parameters/validate")){const parameters=JSON.parse(options.body);payload={ok:true,parameters,canonical_rcp:canonical(parameters),validation:{valid:true,parameters_crc:"27384620"}};}
    else if(path.endsWith("/motor-test/apply")){if(lost)throw new Error("Reply lost");payload={ok:true,result:"UNKNOWN",code:"REPLY_LOST"};}
    else if(path.includes("/motor-test/reconcile?"))payload={ok:true,request_id:pending.request_id,result:confirmed?"APPLIED":"UNKNOWN",code:"BOOT_CHANGED",snapshot};
    else throw new Error("Unexpected request "+path);
    return{ok:status<400,status,json:async()=>structuredClone(payload)};
  };
  const bundled=await build({entryPoints:[fileURLToPath(new URL("../src/features/mower/MowerMotorTestConfig.jsx",import.meta.url))],bundle:true,write:false,platform:"node",format:"cjs",plugins:[{name:"hooks",setup(builder){builder.onResolve({filter:/^react$/},()=>({path:"react",namespace:"mock"}));builder.onLoad({filter:/.*/,namespace:"mock"},()=>({contents:'export const {useState,useRef,useEffect}=globalThis.__configHooks; export default {createElement:(type,props,...children)=>({type,props:{...props,children}})};'}));}}]});
  const compiled=new Module("config-test");compiled._compile(bundled.outputFiles[0].text,"config-test.cjs");
  function render(){do{dirty=false;cursor=0;result=compiled.exports.default({snapshot,fresh:true,operator:{authenticated:true},manual:{phase:"DISCONNECTED",disconnect(){}},refresh(){},onBlocked(){}});while(effects.length)effects.shift()();}while(dirty);}
  async function settle(){for(let i=0;i<20;i++){await Promise.resolve();if(dirty)render();}}
  function nodes(value,found=[]){if(Array.isArray(value))value.forEach(v=>nodes(v,found));else if(value&&typeof value==="object"){found.push(value);nodes(value.props?.children,found);}return found;}
  render();await settle();
  return{calls,storage,
    async edit(parameters){const textarea=nodes(result).find(n=>n.type==="textarea");textarea.props.onChange({target:{value:JSON.stringify(parameters)}});render();await settle();},
    async server(parameters,updates={}){server=parameters;revision=updates.revision??revision;pendingState=updates.pending??pendingState;confirmed=updates.confirmed??confirmed;lost=updates.lost??lost;},
    get tree(){return nodes(result);},async fire(ms){for(const[key,timer]of[...timers])if(timer.ms===ms){timers.delete(key);timer.fn();}await settle();},async apply(){const button=nodes(result).find(n=>n.type==="button"&&JSON.stringify(n.props.children).includes("Mentés roverre"));assert.equal(button.props.disabled,false);await button.props.onClick();await settle();},close(){for(const slot of slots)slot?.cleanup?.();for(const[key,value]of Object.entries(original))globalThis[key]=value;}};
}
test("editor opening and periodic reads send only GET and no automatic save",async()=>{
 const h=await harness();try{await h.fire(350);await h.fire(3000);
 assert.ok(h.calls.every(c=>c.method==="GET"));
 assert.equal(h.tree.find(n=>n.type==="textarea").props.disabled,undefined);
 assert.equal(h.tree.find(n=>n.type==="button"&&JSON.stringify(n.props.children).includes("Mentés roverre")).props.disabled,true);
 }finally{h.close();}
});
test("reordered unchanged input never saves to the rover",async()=>{
 const h=await harness();try{await h.edit(Object.fromEntries(Object.entries(initial).reverse()));await h.fire(350);
 assert.equal(h.tree.find(n=>n.type==="button"&&JSON.stringify(n.props.children).includes("Mentés roverre")).props.disabled,true);
 assert.equal(h.calls.filter(c=>c.path.endsWith("/motor-test/apply")).length,0);
 }finally{h.close();}
});
test("real edit sends one POST and lost response is polled with GET without retry",async()=>{
 const h=await harness();try{const changed=structuredClone(initial);changed.wheel_brake_ma[0]+=1;
 await h.edit(changed);await h.fire(350);await h.apply();await h.fire(500);await h.fire(1000);
 assert.equal(h.calls.filter(c=>c.path.endsWith("/motor-test/apply")).length,1);
 assert.ok(h.calls.filter(c=>c.path.includes("reconcile?")).every(c=>c.method==="GET"));
 assert.equal(h.tree.find(n=>n.type==="textarea").props.disabled,undefined);
 }finally{h.close();}
});
test("new rover revision preserves local edits and shows conflict",async()=>{
 const h=await harness();try{const local=structuredClone(initial);local.wheel_brake_ma[0]+=1;
 await h.edit(local);await h.fire(350);
 const newer=structuredClone(initial);newer.wheel_brake_ma[1]+=2;
 await h.server(newer,{revision:4});await h.fire(3000);
 assert.deepEqual(JSON.parse(h.tree.find(n=>n.type==="textarea").props.value),local);
 assert.ok(h.tree.some(n=>n.props?.role==="alert"));
 assert.equal(h.tree.find(n=>n.type==="button"&&JSON.stringify(n.props.children).includes("Mentés roverre")).props.disabled,true);
 assert.equal(h.calls.filter(c=>c.path.endsWith("/motor-test/apply")).length,0);
 }finally{h.close();}
});
test("temporary null does not erase displayed values; reboot with same values never posts",async()=>{
 const h=await harness();try{await h.server(null);await h.fire(3000);
 assert.deepEqual(JSON.parse(h.tree.find(n=>n.type==="textarea").props.value),initial);
 await h.server(initial,{revision:3});await h.fire(3000);
 assert.ok(h.calls.every(c=>c.method==="GET"));
 }finally{h.close();}
});

test("HTTP reply loss retains correlation and starts GET readback without any POST retry",async()=>{
 const h=await harness();try{const changed=structuredClone(initial);changed.wheel_brake_ma[0]+=1;
 await h.edit(changed);await h.fire(350);await h.server(initial,{lost:true});await h.apply();await h.fire(500);
 assert.equal(h.calls.filter(c=>c.path.endsWith("/motor-test/apply")).length,1);
 assert.ok(h.calls.some(c=>c.path.includes("reconcile?")&&c.method==="GET"));
 }finally{h.close();}
});

test("PENDING keeps stored values visible but never presents them as applied or auto-saves",async()=>{
 const h=await harness();try{await h.server(initial,{pending:true});await h.fire(3000);
 assert.deepEqual(JSON.parse(h.tree.find(n=>n.type==="textarea").props.value),initial);
 const changed=structuredClone(initial);changed.wheel_brake_ma[0]+=1;await h.edit(changed);await h.fire(350);
 assert.equal(h.tree.find(n=>n.type==="button"&&JSON.stringify(n.props.children).includes("Mentés roverre")).props.disabled,true);
 assert.equal(h.calls.filter(c=>c.path.endsWith("/motor-test/apply")).length,0);
 assert.ok(h.tree.some(n=>JSON.stringify(n.props?.children).includes("CONFIG_RECOVERY_REQUIRED")));
 }finally{h.close();}
});
