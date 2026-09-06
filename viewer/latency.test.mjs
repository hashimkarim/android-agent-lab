import {test} from 'node:test';
import assert from 'node:assert/strict';
import {VideoPacketQueue,DirectCanvasRenderer} from './latency.mjs';

const tick=()=>new Promise(r=>setImmediate(r));
test('slow decoding retains bounded work and resumes only at a keyframe',async()=>{
  const writes=[];let unblock;
  const queue=new VideoPacketQueue(async p=>{writes.push(p);if(writes.length===1)await new Promise(r=>unblock=r);},e=>{throw e;},3);
  queue.push({type:'configuration',data:'config'});
  queue.push({type:'data',keyframe:true,id:1});
  for(let id=2;id<40;id++)queue.push({type:'data',keyframe:false,id});
  assert.ok(queue.queue.length<=3);
  queue.push({type:'data',keyframe:true,id:40});
  queue.push({type:'data',keyframe:false,id:41});
  unblock();await tick();
  assert.deepEqual(writes.map(p=>p.id),[undefined,40,41]);
  assert.ok(queue.dropped>30);
});

test('canvas backing storage is resized only when device dimensions change',()=>{
  let writes=0,draws=0,width=300,height=150;
  const canvas={get width(){return width;},set width(x){width=x;writes++;},get height(){return height;},set height(x){height=x;writes++;},getContext(type,options){assert.equal(type,'2d');assert.equal(options.desynchronized,true);return{drawImage(){draws++;}};}};
  const renderer=new DirectCanvasRenderer(canvas);
  for(let n=0;n<60;n++){renderer.setSize(480,960);renderer.draw({});}
  assert.equal(writes,2);assert.equal(draws,60);
  renderer.setSize(960,480);assert.equal(writes,4);
});
