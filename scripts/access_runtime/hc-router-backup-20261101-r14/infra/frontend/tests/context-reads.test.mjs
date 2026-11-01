import assert from 'node:assert/strict';
import {test} from 'node:test';
import {createContextReadStore} from '../src/contextReads.mjs';
function harness(){const requests=[];const store=createContextReadStore((path,options)=>new Promise((resolve,reject)=>requests.push({path,options,resolve,reject})));return {store,requests};}
const tick=async()=>{for(let n=0;n<8;n++)await Promise.resolve();};
test('late poll cannot replace command refresh or clear its request owner',async()=>{
 const {store,requests}=harness();const seen=[];store.subscribe('/a',v=>seen.push(v.n));
 const old=store.read('/a').catch(e=>e.name);await tick();const fresh=store.read('/a',{force:true});await tick();
 requests[0].resolve({n:1});await tick();assert.equal(await old,'SupersededContextRead');
 const joined=store.read('/a');assert.equal(requests.length,2);requests[1].resolve({n:2});
 assert.equal((await fresh).payload.n,2);assert.equal((await joined).payload.n,2);assert.deepEqual(seen,[2]);assert.equal((await store.read('/a')).payload.n,2);
});
test('one subscriber abort does not abort another subscriber request',async()=>{
 const {store,requests}=harness();const a=new AbortController(),b=new AbortController();
 const first=store.read('/a',{signal:a.signal}).catch(e=>e.name);const second=store.read('/a',{signal:b.signal});await tick();a.abort();await tick();
 assert.equal(await first,'AbortError');assert.equal(requests[0].options.signal.aborted,false);requests[0].resolve({n:2});assert.equal((await second).payload.n,2);
});
test('last subscriber abort releases a hung path and rejects a late result',async()=>{
 const {store,requests}=harness();const a=new AbortController();const old=store.read('/a',{signal:a.signal}).catch(e=>e.name);await tick();a.abort();assert.equal(await old,'AbortError');await tick();assert.ok(requests[0].options.signal.aborted);
 const fresh=store.read('/a');await tick();requests[0].resolve({n:1});requests[1].resolve({n:2});assert.equal((await fresh).payload.n,2);
});
test('error releases shared ownership, next request can recover',async()=>{
 const {store,requests}=harness();const first=store.read('/a').catch(e=>e.message);await tick();requests[0].reject(new Error('timeout'));assert.equal(await first,'timeout');const next=store.read('/a');await tick();assert.equal(requests.length,2);requests[1].resolve({n:2});assert.equal((await next).payload.n,2);
});
test('path generations and unsubscribe are independent',async()=>{
 const {store,requests}=harness();let updates=0;const stop=store.subscribe('/a',()=>updates++);const a=store.read('/a'),b=store.read('/b');await tick();stop();requests[0].resolve({n:1});requests[1].resolve({n:2});await a;await b;assert.equal(updates,0);assert.equal((await store.read('/b')).payload.n,2);
});
