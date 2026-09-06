import {test} from 'node:test';
import assert from 'node:assert/strict';
import {createCursors} from './cursors.js';

test('no cursors keeps the system pointer and suspends all overlay work, including after mode changes', t => {
  const frames=new Map(),timers=new Map();let next=1,observer,contexts=0,measurements=0,draws=0;
  const globals={
    requestAnimationFrame:fn=>{const id=next++;frames.set(id,fn);return id;},cancelAnimationFrame:id=>frames.delete(id),
    setTimeout:fn=>{const id=next++;timers.set(id,fn);return id;},clearTimeout:id=>timers.delete(id),
    devicePixelRatio:1,localStorage:{value:'none',getItem(){return this.value;},setItem(_key,value){this.value=value;}},
    ResizeObserver:class{constructor(fn){this.callback=fn;observer=this;}observe(){this.active=true;this.callback();}disconnect(){this.active=false;}}
  };
  const previous=new Map(Object.keys(globals).map(key=>[key,Object.getOwnPropertyDescriptor(globalThis,key)]));
  for(const [key,value] of Object.entries(globals))Object.defineProperty(globalThis,key,{value,configurable:true,writable:true});
  t.after(()=>{for(const [key,descriptor] of previous){if(descriptor)Object.defineProperty(globalThis,key,descriptor);else delete globalThis[key];}});
  const context=new Proxy({}, {get:(_target,key)=>key==='measureText'?()=>({width:30}):()=>{draws++;},set:()=>true});
  const canvas={style:{},dataset:{},getContext(){contexts++;return context;}};
  const screen={style:{},offsetLeft:0,offsetTop:0,getBoundingClientRect(){measurements++;return{width:200,height:400};}};
  const mode={value:''},activity={textContent:''};
  const cursors=createCursors(canvas,screen,mode,activity,'human:test',()=>({width:100,height:200}));
  const receive=(actor,x=20)=>cursors.receive({now:Date.now(),events:[{id:actor,actor,kind:'pointer',persistent:true,points:[x,30],at:Date.now()/1000}]},true);
  const paint=()=>{const work=[...frames.values()];frames.clear();work.forEach(fn=>fn(performance.now()));};
  const select=value=>{mode.value=value;mode.onchange();};
  assert.equal(screen.style.cursor,'default');assert.equal(canvas.hidden,true);
  for(let i=0;i<100;i++){receive('codex:test');observer.callback();}
  assert.equal(contexts,0);assert.equal(measurements,0);assert.equal(draws,0);assert.equal(frames.size,0);assert.equal(timers.size,0);
  select('all');receive('human:test');paint();
  assert.equal(screen.style.cursor,'none');assert.equal(canvas.hidden,false);
  assert.deepEqual(JSON.parse(canvas.dataset.markers).map(c=>[c.shape,c.x]),[['circle',40]]);
  receive('human:test',40);paint();assert.equal(JSON.parse(canvas.dataset.markers)[0].x,80);
  select('agents');receive('codex:test');paint();
  assert.equal(screen.style.cursor,'default');assert.equal(JSON.parse(canvas.dataset.markers)[0].shape,'arrow');
  select('none');const before={contexts,measurements,draws};
  for(let i=0;i<100;i++){receive('codex:test');observer.callback();}
  assert.equal(screen.style.cursor,'default');assert.equal(canvas.dataset.markers,'[]');assert.equal(observer.active,false);
  assert.deepEqual({contexts,measurements,draws},before);assert.equal(frames.size,0);assert.equal(timers.size,0);
});
