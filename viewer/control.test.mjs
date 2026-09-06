import {test} from 'node:test';
import assert from 'node:assert/strict';
import {LiveControl} from './control.mjs';
import {ViewerOptions} from './options.mjs';
import {ScrcpyControlMessageSerializer} from '@yume-chan/scrcpy';

function fixture() {
  const calls=[],locks=[],events=[];let owned=true;
  const controller=new Proxy({}, {get:(_t,name)=>async value=>{calls.push({name,value});}});
  const control=new LiveControl({controller,broker:{acquire:async e=>locks.push(['acquire',e]),release:async(e,ok)=>locks.push(['release',e,ok]),close(){}},
    owns:()=>owned,size:()=>({width:568,height:1280}),physicalSize:()=>({width:1080,height:2424}),broadcast:e=>events.push(e)});
  const point=(phase,x=100,y=200)=>({kind:'pointer',phase,x,y,width:568,height:1280,actor:'human:test'});
  return {control,calls,locks,events,point,revoke:()=>{owned=false;}};
}

test('motion reaches scrcpy before release with one shared lock for the entire gesture',async()=>{
  const f=fixture(),client={};
  await f.control.submit(client,f.point('down'));
  for(let i=0;i<20;i++) await f.control.submit(client,f.point('move',100+i,200+i));
  assert.equal(f.calls.length,21);assert.equal(f.calls.at(-1).value.action,2);
  assert.equal(f.locks.length,1);assert.equal(f.locks[0][0],'acquire');
  await assert.rejects(f.control.submit({},f.point('down')),/another pointer/i);
  await assert.rejects(f.control.submit({},f.point('up')),/does not own/i);
  await f.control.submit(client,f.point('up',120,220));
  assert.equal(f.calls.at(-1).value.action,1);assert.equal(f.calls.at(-1).value.pressure,0);
  assert.equal(f.locks.length,2);assert.equal(f.locks[1][0],'release');
});

test('hover emits live visual presence without Android input or ownership renewal',async()=>{
  const f=fixture(),client={};
  await f.control.submit(client,{...f.point('move'),kind:'hover'});
  await f.control.submit(client,{...f.point('move',300,400),kind:'hover'});
  assert.equal(f.calls.length,0);assert.equal(f.locks.length,0);
  const event=f.events.at(-1).events[0];assert.equal(event.persistent,true);assert.equal(event.phase,'hover');
  assert.ok(event.points[0]>500);
  await f.control.disconnect(client);assert.equal(f.events.at(-1).events[0].phase,'leave');
});

test('disconnect cancels the device touch and releases the lock',async()=>{
  const f=fixture(),client={};await f.control.submit(client,f.point('down'));
  await f.control.disconnect(client);
  assert.equal(f.calls.at(-1).value.action,3);assert.equal(f.control.active,null);
  assert.equal(f.locks.at(-1)[0],'release');
  await f.control.submit({},f.point('down'));await f.control.close();
  assert.equal(f.calls.at(-1).value.action,3);
});

test('revoked or read-only sessions cannot inject and stale frame coordinates are rejected',async()=>{
  const f=fixture();
  await assert.rejects(f.control.submit({}, {...f.point('down'),width:1280,height:568}),/size changed/);
  f.revoke();await assert.rejects(f.control.submit({},f.point('down')),/claim/);
  assert.equal(f.calls.length,0);assert.equal(f.locks.length,0);
  const ro=fixture();ro.control.controller=undefined;
  await assert.rejects(ro.control.submit({},ro.point('down')),/read-only/);
});

test('Unicode clipboard and navigation use scrcpy; activity never contains the text',async()=>{
  const f=fixture();
  await f.control.submit({}, {kind:'clipboard',text:'Private 🙂 密码',actor:'codex:test'});
  await f.control.submit({}, {kind:'key',key:'HOME',actor:'codex:test'});
  assert.equal(f.calls[0].name,'setClipboard');assert.equal(f.calls[0].value.content,'Private 🙂 密码');
  assert.equal(f.calls[1].value.action,0);assert.equal(f.calls[2].value.action,1);
  assert.equal(f.calls[1].value.keyCode,3);assert.ok(!JSON.stringify(f.events).includes('Private'));
  assert.ok(!JSON.stringify(f.locks).includes('Private'));
});

test('the pinned scrcpy adapter can paste Unicode with clipboard autosync disabled',()=>{
  const options=new ViewerOptions({control:true,clipboardAutosync:false});
  assert.equal(options.clipboard,undefined);
  const text='Hello 🙂 密码 %s';
  const packet=new ScrcpyControlMessageSerializer(options).setClipboard({sequence:0n,content:text,paste:true});
  assert.ok(packet instanceof Uint8Array);
  assert.equal(packet[0],9);assert.equal(packet[9],1);
  assert.equal(new TextDecoder().decode(packet.subarray(14)),text);
});

test('disconnect queued during acquisition clears the final cursor and operation lock',async()=>{
  const f=fixture(),client={};
  const down=f.control.submit(client,f.point('down'));
  const disconnect=f.control.disconnect(client);
  await Promise.all([down,disconnect]);
  assert.equal(f.control.active,null);assert.equal(f.control.presence.size,0);
  assert.equal(f.events.at(-1).events[0].phase,'leave');
  assert.equal(f.locks.at(-1)[0],'release');
});

test('congested movement coalesces without losing press/release or final position',async()=>{
  const f=fixture(),client={};let acquired;
  f.control.broker.acquire=()=>new Promise(r=>{acquired=r;});
  const down=f.control.submit(client,f.point('down'));
  await new Promise(r=>setImmediate(r));
  const moves=Array.from({length:100},(_,i)=>f.control.submit(client,f.point('move',100+i,200+i)));
  const up=f.control.submit(client,f.point('up',200,300));
  assert.ok(f.control.queued<=3);
  acquired();await Promise.all([down,...moves,up]);
  assert.deepEqual(f.calls.map(c=>c.value.action),[0,2,1]);
  assert.equal(f.calls[1].value.pointerX,199);
  assert.equal(f.control.active,null);
});
