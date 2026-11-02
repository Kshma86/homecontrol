import assert from "node:assert/strict";
import { test } from "node:test";
import { fileURLToPath } from "node:url";
import Module from "node:module";
import { build } from "esbuild";

async function harness() {
  const slots = [], effects = [], timers = [], sockets = [];
  let cursor = 0, dirty = false, result, time = 100;
  let input = { snapshot: { identity: { esp_boot: "0123456789ABCDEF", stm_boot: "FEDCBA9876543210", update_locked: false },
    connection: { status: "LIVE" }, freshness: { fresh: true, effective_age_ms: 10 }, capabilities: { manual: true, manual_erpm: true },
    state: { state: "IDLE", stopped: true, control_epoch: 4 } }, receivedAt: 100, error: "", authenticated: true };
  const original = Object.fromEntries(["window", "document", "location", "performance", "WebSocket", "__manualHooks"].map((key) => [key, globalThis[key]]));
  const listeners = {};
  globalThis.__manualHooks = {
    useState(initial) { const i = cursor++; if (!slots[i]) slots[i] = { value: initial }; return [slots[i].value, (value) => { slots[i].value = typeof value === "function" ? value(slots[i].value) : value; dirty = true; }]; },
    useRef(initial) { const i = cursor++; if (!slots[i]) slots[i] = { current: initial }; return slots[i]; },
    useEffect(callback, deps) { const i = cursor++; if (!slots[i] || deps.some((v, at) => !Object.is(v, slots[i].deps[at]))) effects.push(() => { slots[i]?.cleanup?.(); slots[i] = { deps, cleanup: callback() }; }); },
  };
  globalThis.window = { setInterval(fn, ms) { timers.push({ fn, ms }); return timers.length; }, clearInterval() {},
    addEventListener(name, fn) { listeners[name] = fn; }, removeEventListener() {} };
  globalThis.document = { visibilityState: "visible", addEventListener(name, fn) { listeners[name] = fn; }, removeEventListener() {} };
  globalThis.location = { protocol: "http:", host: "hc.test" };
  globalThis.performance = { now: () => time };
  class Socket {
    static OPEN = 1;
    constructor() { this.readyState = 0; this.bufferedAmount = 0; this.sent = []; sockets.push(this); }
    send(raw) { this.sent.push(JSON.parse(raw)); }
    close() { this.readyState = 3; }
  }
  globalThis.WebSocket = Socket;
  const bundled = await build({ entryPoints: [fileURLToPath(new URL("../src/features/mower/useMowerManual.js", import.meta.url))], bundle: true, write: false, platform: "node", format: "cjs",
    plugins: [{ name: "mock-hooks", setup(builder) {
      builder.onResolve({ filter: /^react$/ }, () => ({ path: "react", namespace: "mock" }));
      builder.onLoad({ filter: /.*/, namespace: "mock" }, () => ({ contents: "export const {useState,useRef,useEffect}=globalThis.__manualHooks;" }));
    } }] });
  const compiled = new Module("manual-hook"); compiled._compile(bundled.outputFiles[0].text, "manual-hook.cjs");
  function render() { do { dirty = false; cursor = 0; result = compiled.exports.default(input); while (effects.length) effects.shift()(); } while (dirty); }
  function act(fn) { fn(result); render(); }
  render();
  return { sockets, timers, get value() { return result; }, act,
    claim(onlyClaim=false) { act((value) => value.connect()); const socket = sockets.at(-1); socket.readyState = 1; socket.onopen(); render();
      if(onlyClaim)return socket;
      socket.onmessage({ data: JSON.stringify({ type: "claimed", lease_id: 7, control_epoch: 5, lease_ms: 350, drive_mode: "ERPM", motor_erpm_limits: [1000,1000,1000], max_linear_mm_s: 0, max_yaw_mdeg_s: 0 }) }); render(); return socket; },
    tick() { time += timers[0].ms; timers[0].fn(); render(); },
    blur() { listeners.blur(); render(); },
    input(updates) { input = { ...input, ...updates }; render(); },
    close() { for (const slot of slots) slot?.cleanup?.(); for (const [key, value] of Object.entries(original)) globalThis[key] = value; },
  };
}

test("ERPM hook is zero after claim, sends only under held deadman, clears all intent on blur and reconnect", async () => {
  const h = await harness();
  try {
    assert.equal(h.sockets.length, 0);
    const socket = h.claim();
    assert.equal(h.value.phase, "ACTIVE"); assert.equal(h.timers[0].ms, 75);
    h.tick(); assert.equal(socket.sent.length, 2); assert.equal(socket.sent.at(-1).deadman, false); // periodic zero keeps the claimed lease alive
    h.act((value) => value.setIntent({ left: 100, right: -100, third: 300, thirdEnabled: true }));
    h.act((value) => value.hold()); h.tick();
    assert.deepEqual(socket.sent.at(-1), { type: "drive_erpm", lease_id: 7, control_epoch: 5, seq: 2, left_erpm: 100, right_erpm: -100, third_erpm: 300, deadman: true });
    h.blur(); assert.equal(h.value.held, false); assert.equal(h.value.intent.thirdEnabled, false);
    assert.deepEqual([socket.sent.at(-1).left_erpm,socket.sent.at(-1).right_erpm,socket.sent.at(-1).third_erpm,socket.sent.at(-1).deadman], [0,0,0,false]);
    h.act((value) => value.hold()); h.tick(); assert.equal(socket.sent.at(-1).third_erpm, 0);
    h.act((value) => value.disconnect()); assert.equal(socket.sent.at(-1).type, "release");
    const second = h.claim(); h.tick(); assert.equal(second.sent.length, 2); assert.equal(h.value.held, false);
  } finally { h.close(); }
});

test("link errors, stale capability and logout never auto-reclaim or replay motion", async () => {
  for (const failure of ["link", "logout", "capability", "buffer"]) {
    const h = await harness();
    try {
      const socket = h.claim(); h.act((value) => value.setIntent({ left:100,right:100,third:500,thirdEnabled:true })); h.act((value) => value.hold());
      if (failure === "link") { socket.onerror(); h.act(() => {}); }
      if (failure === "logout") h.input({ authenticated: false });
      if (failure === "capability") h.input({ snapshot: { capabilities: { manual:false } } });
      if (failure === "buffer") socket.bufferedAmount = 2049;
      h.tick(); assert.equal(h.value.phase, "DISCONNECTED"); assert.equal(h.sockets.length, 1);
      h.tick(); assert.equal(h.sockets.length, 1); assert.equal(h.value.intent.thirdEnabled, false);
      assert.ok(socket.sent.every((frame) => frame.type !== "drive_erpm" || frame.third_erpm === 0));
    } finally { h.close(); }
  }
});

test("short WS backpressure skips stale targets and sends only latest intent after recovery",async()=>{
  const h=await harness();try{
    const socket=h.claim(); h.act(value=>value.setIntent({left:100,right:100,third:0,thirdEnabled:false}));h.act(value=>value.hold());
    socket.bufferedAmount=10;h.tick();assert.equal(h.value.phase,"ACTIVE");assert.equal(socket.sent.length,1);
    h.act(value=>value.setIntent({left:200,right:200,third:0,thirdEnabled:false}));socket.bufferedAmount=0;h.tick();
    assert.equal(socket.sent.at(-1).left_erpm,200);assert.equal(socket.sent.filter(frame=>frame.type==="drive_erpm").length,1);
    socket.bufferedAmount=10;h.tick();h.tick();h.tick();assert.equal(h.value.phase,"DISCONNECTED");
  }finally{h.close();}
});

test("simplify11 claims directly from DISARMED and never restores intent after peer change",async()=>{
 const h=await harness();try{
  const snapshot={simple_control:true,identity:{mode:"MOTOR_TEST",manual_claim_from_disarmed:true,test_manual_control:true,esp_boot:"0123456789ABCDEF",stm_boot:"FEDCBA9876543210",update_locked:true},connection:{status:"LIVE"},freshness:{fresh:true,effective_age_ms:10},capabilities:{manual:true,manual_erpm:true},state:{state:"DISARMED",stopped:false,control_epoch:4,store:"EMPTY"}};
  h.input({snapshot}); const socket=h.claim();
  assert.equal(socket.sent[0].type,"claim");assert.equal(socket.sent[0].control_epoch,4);
  h.tick();assert.equal(socket.sent.at(-1).control_epoch,5);assert.equal(socket.sent.at(-1).third_erpm,0);assert.equal(socket.sent.at(-1).deadman,false);
  h.input({snapshot:{...snapshot,identity:{...snapshot.identity,stm_boot:"1111111111111111"}}});h.tick();
  assert.equal(h.value.phase,"DISCONNECTED");h.tick();assert.equal(h.sockets.length,1);assert.equal(h.value.intent.left,0);
 }finally{h.close();}
});

test("idle observed while CLAIMING grants no lease, never repeats claim, and waits for claimed",async()=>{
 const h=await harness();try{
  const socket=h.claim(true);
  h.act(()=>socket.onmessage({data:JSON.stringify({type:"observed",lease_id:0,last_input_seq:0,state:"IDLE",stopped:true})}));
  assert.equal(h.value.phase,"CLAIMING");assert.equal(h.value.lease,null);
  h.act(value=>value.hold());h.tick();assert.equal(h.value.held,false);
  assert.equal(socket.sent.length,1);assert.equal(socket.sent[0].type,"claim");
  h.act(()=>socket.onmessage({data:JSON.stringify({type:"claimed",lease_id:7,control_epoch:5,lease_ms:350,drive_mode:"ERPM",motor_erpm_limits:[1000,1000,0],max_linear_mm_s:0,max_yaw_mdeg_s:0})}));
  assert.equal(h.value.phase,"ACTIVE");assert.equal(h.value.held,false);
  h.tick();assert.equal(socket.sent.at(-1).deadman,false);assert.equal(socket.sent.at(-1).third_erpm,0);
 }finally{h.close();}
});

test("a claimed reply from the old connection cannot activate after an ESP reboot",async()=>{
 const h=await harness();try{
  const socket=h.claim(true);
  h.input({snapshot:{identity:{esp_boot:"1111111111111111",stm_boot:"FEDCBA9876543210"},connection:{status:"LIVE"},freshness:{fresh:true,effective_age_ms:10},capabilities:{manual:true,manual_erpm:true},state:{state:"IDLE",stopped:true,control_epoch:4}}});
  h.act(()=>socket.onmessage({data:JSON.stringify({type:"claimed",lease_id:7,control_epoch:5,lease_ms:350,drive_mode:"ERPM",motor_erpm_limits:[1000,1000,0],max_linear_mm_s:0,max_yaw_mdeg_s:0})}));
  assert.equal(h.value.phase,"DISCONNECTED");assert.equal(h.value.lease,null);assert.equal(h.sockets.length,1);
  assert.ok(socket.sent.every(frame=>frame.type==="claim"));
 }finally{h.close();}
});

test("manual heartbeat leaves room under the 20 messages per second native cap",async()=>{
 const h=await harness();try{
  const socket=h.claim();
  for(let i=0;i<12;i++)h.tick();
  for(let i=0;i<3;i++)h.act(value=>value.zero());
  assert.equal(h.timers[0].ms,75);assert.ok(socket.sent.length<=20);
  assert.ok(socket.sent.filter(frame=>frame.type==="drive_erpm").every(frame=>frame.deadman===false));
 }finally{h.close();}
});

test("an active matching lease survives a false new-claim capability flag",async()=>{
 const h=await harness();try{
  const socket=h.claim();
  h.input({snapshot:{identity:{esp_boot:"0123456789ABCDEF",stm_boot:"FEDCBA9876543210",update_locked:false},connection:{status:"LIVE"},freshness:{fresh:true,effective_age_ms:10},capabilities:{manual:false},state:{state:"MANUAL",control_epoch:5,manual_lease_id:7}}});
  h.tick();assert.equal(h.value.phase,"ACTIVE");assert.equal(socket.sent.at(-1).deadman,false);
 }finally{h.close();}
});

test("native IDLE with zero lease closes the session without a protocol error or reconnect",async()=>{
 const h=await harness();try{
  const socket=h.claim();
  h.act(()=>socket.onmessage({data:JSON.stringify({type:"observed",lease_id:0,last_input_seq:0,state:"IDLE",stopped:true})}));
  assert.equal(h.value.phase,"DISCONNECTED");assert.match(h.value.message,/STM lezárta/);
  h.tick();assert.equal(h.sockets.length,1);assert.equal(h.value.held,false);
 }finally{h.close();}
});
