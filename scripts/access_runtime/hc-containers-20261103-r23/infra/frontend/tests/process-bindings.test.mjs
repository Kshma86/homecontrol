import assert from "node:assert/strict";
import { test } from "node:test";
import { fileURLToPath } from "node:url";
import Module from "node:module";
import { build } from "esbuild";

// Bundle the real helper and its real formatter imports, as the UI does.
const result = await build({entryPoints:[fileURLToPath(new URL("../src/entityHelpers.js",import.meta.url))],
  bundle:true,write:false,platform:"node",format:"cjs"});
const compiled = new Module(fileURLToPath(import.meta.url));
compiled._compile(result.outputFiles[0].text, fileURLToPath(import.meta.url));
const {selectedProcessDevice} = compiled.exports;
const key="marten_power_socket", a={entity_id:11}, b={entity_id:22};

test("invalid explicit role cannot select the UI name-based fallback",()=>{
  const state={devices:[a,b],process_bindings:{[key]:{configuration_state:"invalid",selected_entity_id:null,selected_entity:null}}};
  assert.equal(selectedProcessDevice(state,key,()=>b),null);
});
test("authoritative missing fallback remains unavailable",()=>{
  const state={devices:[b],process_bindings:{[key]:{configuration_state:"not_configured",selected_entity_id:null}}};
  assert.equal(selectedProcessDevice(state,key,()=>b),null);
});
test("valid explicit and server-selected legacy targets keep their identity",()=>{
  for(const configuration_state of ["valid","not_configured"]){
    const state={devices:[a,b],process_bindings:{[key]:{configuration_state,selected_entity_id:11}}};
    assert.equal(selectedProcessDevice(state,key,()=>b),a);
  }
});
test("old payload without a binding section retains initial compatibility",()=>{
  assert.equal(selectedProcessDevice({devices:[b]},key,()=>b),b);
});
