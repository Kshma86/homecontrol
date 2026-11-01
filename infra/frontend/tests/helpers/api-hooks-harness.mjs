import {fileURLToPath} from 'node:url';
import Module from 'node:module';
import {build} from 'esbuild';
export async function harness(initialPath='/api/context/a',initialOptions={}){
 const slots=[],effects=[],timers=new Map(),requests=[],listeners=new Map();let cursor=0,dirty=false,result,path=initialPath,options=initialOptions,closed=false,writesAfterClose=0,id=0;
 const keys=['window','document','fetch','__apiHooks'];const saved=Object.fromEntries(keys.map(k=>[k,globalThis[k]]));
 const changed=(a,b)=>!a||a.length!==b.length||b.some((x,i)=>!Object.is(x,a[i]));
 globalThis.__apiHooks={
  useState(value){const i=cursor++;if(!slots[i])slots[i]={value:typeof value==='function'?value():value};return[slots[i].value,v=>{if(closed)writesAfterClose++;slots[i].value=typeof v==='function'?v(slots[i].value):v;dirty=true;}];},
  useRef(value){const i=cursor++;if(!slots[i])slots[i]={current:value};return slots[i];},
  useEffect(fn,deps){const i=cursor++;if(changed(slots[i]?.deps,deps))effects.push(()=>{slots[i]?.cleanup?.();slots[i]={deps,cleanup:fn()};});},
  useMemo(fn,deps){const i=cursor++;if(changed(slots[i]?.deps,deps))slots[i]={deps,value:fn()};return slots[i].value;},
  useCallback(fn,deps){return this.useMemo(()=>fn,deps);},
 };
 globalThis.window={setInterval(fn,ms){timers.set(++id,{fn,ms});return id;},clearInterval(id){timers.delete(id);}};
 globalThis.document={visibilityState:'visible',addEventListener(n,fn){listeners.set(n,fn);},removeEventListener(n,fn){if(listeners.get(n)===fn)listeners.delete(n);}};
 globalThis.fetch=(path,options)=>new Promise((resolve,reject)=>requests.push({path,options,resolve,reject}));
 const bundled=await build({entryPoints:[fileURLToPath(new URL('../../src/apiClient.js',import.meta.url))],bundle:true,write:false,platform:'node',format:'cjs',plugins:[{name:'hooks',setup(b){b.onResolve({filter:/^react$/},()=>({path:'react',namespace:'mock'}));b.onLoad({filter:/.*/,namespace:'mock'},()=>({contents:'const h=globalThis.__apiHooks; export const useState=h.useState.bind(h),useRef=h.useRef.bind(h),useEffect=h.useEffect.bind(h),useMemo=h.useMemo.bind(h),useCallback=h.useCallback.bind(h);'}));}}]});
 const compiled=new Module('api-hooks');compiled._compile(bundled.outputFiles[0].text,'api-hooks.cjs');
 function render(){let limit=0;do{if(++limit>20)throw Error('render loop');dirty=false;cursor=0;result=compiled.exports.usePolledContext(path,options);while(effects.length)effects.shift()();}while(dirty);}
 async function settle(){for(let i=0;i<20;i++){await Promise.resolve();if(dirty&&!closed)render();}}
 render();await settle();
 return{requests,exports:compiled.exports,get value(){return result;},get writesAfterClose(){return writesAfterClose;},async respond(index,data){requests[index].resolve({ok:true,status:200,text:async()=>JSON.stringify(data)});await settle();},async changePath(value){path=value;render();await settle();},async visibility(value){document.visibilityState=value;listeners.get('visibilitychange')?.();await settle();},async poll(){for(const t of [...timers.values()])t.fn();await settle();},settle,async unmount(){for(const s of slots)s?.cleanup?.();closed=true;await settle();},async close(){if(!closed)await this.unmount();for(const[k,v]of Object.entries(saved))globalThis[k]=v;}};
}
