import {WebCodecsVideoDecoder, BitmapVideoFrameRenderer} from '@yume-chan/scrcpy-decoder-webcodecs';
import {createCursors} from './cursors.js';
window.addEventListener('hashchange', () => location.reload());
const $ = id => document.getElementById(id);
const key = new URLSearchParams(location.hash.slice(1)).get('key');
const browserActor = sessionStorage.getItem('adb-video-actor') || `human:browser-${crypto.randomUUID().slice(0,8)}`;
sessionStorage.setItem('adb-video-actor', browserActor);
const actor = new URLSearchParams(location.hash.slice(1)).get('actor') || browserActor;
const canvas = $('screen'), status = $('status');
let decoder, writer, settings, socket, control, pressed = null, lastPoint, motion = null, frameTask = 0, ready = false;
let nextId = 0, zoom = null, currentTool, recording, recordingTimer;
const pending = new Map();
function dimensions() {
  if (!settings) return null;
  let {width,height} = settings;
  if ((canvas.width > canvas.height) !== (width > height)) [width,height]=[height,width];
  return {width,height};
}
const cursors = createCursors($('cursors'), canvas, $('cursor-mode'), $('activity'), actor, dimensions);
function fit() {
  if (!ready) return;
  const space=$('viewport'), style=getComputedStyle(space);
  const scale=zoom ?? Math.min((space.clientWidth-parseFloat(style.paddingLeft)*2)/canvas.width,(space.clientHeight-parseFloat(style.paddingTop)*2)/canvas.height);
  canvas.style.width=Math.max(1,canvas.width*scale)+'px';canvas.style.height=Math.max(1,canvas.height*scale)+'px';
}
new ResizeObserver(fit).observe($('viewport'));
$('fit').onclick=()=>{zoom=null;fit();};
$('zoom-in').onclick=()=>{zoom=Math.min(3,(zoom ?? canvas.clientWidth/canvas.width)*1.25);fit();};
$('zoom-out').onclick=()=>{zoom=Math.max(.1,(zoom ?? canvas.clientWidth/canvas.width)/1.25);fit();};
$('fullscreen').onclick=()=>{(document.fullscreenElement ? document.exitFullscreen() : document.documentElement.requestFullscreen()).catch(e=>status.textContent=e.message);};
function enabled() {
  document.querySelectorAll('[data-key],[data-command],[data-tool],[data-rotation],#install-apk,#screenshot,#send-text,#text').forEach(e=>e.disabled=!settings?.control || control?.readyState!==WebSocket.OPEN);
}
async function api(path, data, binary=false) {
  const response = await fetch(path, {method:data ? 'POST':'GET', headers:{'X-ADB-Preview-Key':key || '', ...(data ? {'Content-Type':binary ? 'application/vnd.android.package-archive' : 'application/json'}:{})}, ...(data ? {body:binary ? data : JSON.stringify(data)}:{})});
  const result = await response.json();
  if (!response.ok) throw new Error(result.error);
  return result;
}
function send(data, reliable=true) {
  if (control?.readyState!==WebSocket.OPEN || (data.kind!=='hover' && !settings?.control)) return Promise.resolve(false);
  // Preserve down/up; stale movement never accumulates behind an obstructed socket.
  if (control.bufferedAmount>65536 && (data.kind==='hover' || data.phase==='move')) return Promise.resolve(false);
  const id = reliable ? ++nextId : undefined;
  const result = reliable ? new Promise(resolve=>{
    const timer=setTimeout(()=>{pending.delete(id);status.textContent='Input response timed out.';resolve(false);},10000);
    pending.set(id,{resolve,timer,started:performance.now()});
  }) : Promise.resolve(true);
  control.send(JSON.stringify({...data,actor,id}));
  return result;
}
function point(event) {
  const r=canvas.getBoundingClientRect();
  return {x:Math.max(0,Math.min(canvas.width-1,Math.round((event.clientX-r.left)/r.width*canvas.width))),
    y:Math.max(0,Math.min(canvas.height-1,Math.round((event.clientY-r.top)/r.height*canvas.height))),width:canvas.width,height:canvas.height};
}
function localPointer(p,phase='hover') {
  const d=dimensions();if (!d) return;
  cursors.receive({now:Date.now(),events:[{id:'local-pointer',actor,kind:'pointer',phase,persistent:true,pressed:pressed!==null,
    points:[p.x/p.width*d.width,p.y/p.height*d.height],at:Date.now()/1000}]},true);
}
function flushMotion() {
  cancelAnimationFrame(frameTask);frameTask=0;
  if (!motion) return;
  const p=motion;motion=null;
  if (pressed!==null) send({kind:'pointer',phase:'move',...p},false);
  else send({kind:'hover',...p},false);
}
canvas.onpointermove=e=>{
  if (!ready || e.pointerType==='touch' && pressed===null) return;
  lastPoint=point(e);localPointer(lastPoint);motion=lastPoint;
  if (!frameTask) frameTask=requestAnimationFrame(flushMotion);
};
canvas.onpointerenter=e=>{if (ready) {lastPoint=point(e);localPointer(lastPoint);send({kind:'hover',...lastPoint},false);}};
canvas.onpointerleave=()=>{if (pressed===null && lastPoint) {flushMotion();localPointer(lastPoint,'leave');send({kind:'hover',phase:'leave'},false);}};
canvas.onpointerdown=e=>{
  if (!ready || !settings?.control || pressed!==null) return;
  if (e.button===2) {e.preventDefault();send({kind:'key',key:'BACK'});return;}
  if (e.button!==0) return;
  e.preventDefault();flushMotion();canvas.focus();pressed=e.pointerId;lastPoint=point(e);canvas.setPointerCapture(e.pointerId);
  localPointer(lastPoint,'down');send({kind:'pointer',phase:'down',...lastPoint});
};
function release(phase='cancel',event) {
  if (pressed===null) return;
  flushMotion();const id=pressed;pressed=null;
  if (event) lastPoint=point(event);
  if (canvas.hasPointerCapture(id)) canvas.releasePointerCapture(id);
  localPointer(lastPoint,phase);send({kind:'pointer',phase,...lastPoint});
}
canvas.onpointerup=e=>release('up',e);
canvas.onpointercancel=()=>release();
canvas.onlostpointercapture=()=>release();
canvas.oncontextmenu=e=>e.preventDefault();
window.addEventListener('blur',()=>{release();if (lastPoint) {localPointer(lastPoint,'leave');send({kind:'hover',phase:'leave'},false);}});
document.addEventListener('visibilitychange',()=>{if (document.hidden) release();});
canvas.addEventListener('wheel',e=>{
  if (!ready || !settings?.control) return;e.preventDefault();lastPoint=point(e);
  const unit=e.deltaMode===1 ? 1/3 : e.deltaMode===2 ? 1 : 1/100;
  send({kind:'scroll',...lastPoint,scrollX:Math.max(-1,Math.min(1,-e.deltaX*unit)),scrollY:Math.max(-1,Math.min(1,-e.deltaY*unit))});
},{passive:false});
canvas.onkeydown=e=>{
  if (!settings?.control) return;
  if ((e.ctrlKey || e.metaKey) && e.code==='KeyV') return; // Native paste event supplies clipboard text.
  const keys={Backspace:'DEL',Enter:'ENTER',Tab:'TAB',Escape:'BACK',ArrowLeft:'DPAD_LEFT',ArrowRight:'DPAD_RIGHT',ArrowUp:'DPAD_UP',ArrowDown:'DPAD_DOWN'};
  const meta=(e.shiftKey?1:0)|(e.altKey?2:0)|(e.ctrlKey?0x1000:0)|(e.metaKey?0x10000:0);
  if (keys[e.key] || e.ctrlKey || e.metaKey || e.altKey) {e.preventDefault();send({kind:'key',key:keys[e.key],code:e.code,meta});}
  else if (e.key.length===1) {e.preventDefault();send({kind:'text',text:e.key});}
};
canvas.onpaste=e=>{const text=e.clipboardData?.getData('text/plain');if (text) {e.preventDefault();send({kind:'clipboard',text});}};
document.querySelectorAll('[data-key]').forEach(b=>b.onclick=()=>send({kind:'key',key:b.dataset.key}));
document.querySelectorAll('[data-command]').forEach(b=>b.onclick=()=>send({kind:'command',command:b.dataset.command}));
document.querySelectorAll('[data-rotation]').forEach(b=>b.onclick=async()=>{
  b.disabled=true;
  try {await api('/devtools',{tool:b.dataset.rotation});status.textContent=b.dataset.rotation==='rotate'?'Orientation locked · Auto-rotate restores sensor rotation.':'Auto-rotate enabled.';}
  catch(e){status.textContent=e.message;}finally{enabled();}
});
$('text-form').onsubmit=async e=>{e.preventDefault();const input=$('text'),value=input.value;if (value && await send({kind:'clipboard',text:value}) && input.value===value) input.value='';};
$('reload').onclick=()=>location.reload();
function download(blob,name) {
  const url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),30000);
}
const stamp=()=>new Date().toISOString().replace(/[:.]/g,'-');
async function runTool(tool) {
  currentTool=tool;$('tool-panel').hidden=false;$('tool-title').textContent=tool==='hierarchy'?'UI hierarchy':tool==='logcat'?'Logcat · latest 500 lines':'Device tool';$('tool-output').textContent='Loading…';
  $('tool-refresh').disabled=true;
  try {const result=await api('/devtools',{tool});$('tool-output').textContent=result.text || 'Done.';status.textContent='Device tool completed.';}
  catch(e){$('tool-output').textContent=e.message;status.textContent=e.message;}
  finally{$('tool-refresh').disabled=false;}
}
document.querySelectorAll('[data-tool]').forEach(b=>b.onclick=()=>runTool(b.dataset.tool));
$('tool-close').onclick=()=>{$('tool-panel').hidden=true;};
$('tool-refresh').onclick=()=>runTool(currentTool);
$('tool-save').onclick=()=>download(new Blob([$('tool-output').textContent],{type:currentTool==='hierarchy'?'application/xml':'text/plain'}),`${currentTool}-${stamp()}.${currentTool==='hierarchy'?'xml':'txt'}`);
$('screenshot').onclick=async()=>{
  $('screenshot').disabled=true;
  try{const result=await api('/devtools',{tool:'screenshot'});download(new Blob([Uint8Array.from(atob(result.image),c=>c.charCodeAt(0))],{type:'image/png'}),`android-${stamp()}.png`);status.textContent='Full-resolution screenshot saved.';}
  catch(e){status.textContent=e.message;}finally{enabled();}
};
$('install-apk').onclick=()=>$('apk-file').click();
$('apk-file').onchange=async()=>{
  const file=$('apk-file').files[0];if (!file) return;
  currentTool='install';$('tool-refresh').disabled=true;
  $('tool-panel').hidden=false;$('tool-title').textContent='Install APK';$('tool-output').textContent=`Installing ${file.name}…`;$('install-apk').disabled=true;
  try{if (file.size>200*1024*1024) throw Error('APK exceeds 200 MB; use the coordinated CLI.');const result=await api('/devtools/install',file,true);$('tool-output').textContent=result.text || 'Installed.';}
  catch(e){$('tool-output').textContent=e.message;}finally{$('apk-file').value='';enabled();}
};
$('record').onclick=()=>{
  if (recording){recording.stop();return;}
  if (!ready || !window.MediaRecorder) {status.textContent='Screen recording is unavailable.';return;}
  const stream=canvas.captureStream(60),chunks=[];let bytes=0;
  try {recording=new MediaRecorder(stream,{...(MediaRecorder.isTypeSupported('video/webm;codecs=vp8')?{mimeType:'video/webm;codecs=vp8'}:{}),videoBitsPerSecond:6000000});}
  catch(e){stream.getTracks().forEach(t=>t.stop());status.textContent=e.message;return;}
  recording.ondataavailable=e=>{if (e.data.size) {chunks.push(e.data);bytes+=e.data.size;if (bytes>128*1024*1024 && recording?.state==='recording') recording.stop();}};
  recording.onstop=()=>{clearTimeout(recordingTimer);stream.getTracks().forEach(t=>t.stop());download(new Blob(chunks,{type:'video/webm'}),`android-${stamp()}.webm`);recording=null;$('record').classList.remove('recording');$('record').setAttribute('aria-label','Record screen');status.textContent='Screen recording saved.';};
  recording.start(1000);recordingTimer=setTimeout(()=>recording?.stop(),300000);$('record').classList.add('recording');$('record').setAttribute('aria-label','Stop recording');status.textContent='Recording phone video · click Record to stop (5 min / 128 MB limit).';
};
enabled();
try {
  if (!WebCodecsVideoDecoder.isSupported) throw Error('Use a Chromium browser with WebCodecs support.');
  settings=await api('/status');$('device').textContent=settings.serial;
  const prefix=`${location.protocol==='https:'?'wss':'ws'}://${location.host}`;
  control=new WebSocket(`${prefix}/control`,`adb-control.${key}`);
  control.onopen=enabled;
  control.onmessage=e=>{
    const result=JSON.parse(e.data),p=pending.get(result.id);
    if (p){clearTimeout(p.timer);pending.delete(result.id);p.resolve(result.ok);canvas.dataset.inputRtt=(performance.now()-p.started).toFixed(1);}
    if (!result.ok){status.textContent=result.error;release();}
  };
  control.onclose=()=>{pressed=null;enabled();for (const p of pending.values()){clearTimeout(p.timer);p.resolve(false);}pending.clear();};
  socket=new WebSocket(`${prefix}/stream`,`adb-video.${key}`);socket.binaryType='arraybuffer';
  let decoding=Promise.resolve();
  socket.onmessage=event=>{
    if (typeof event.data==='string') {
      const message=JSON.parse(event.data);
      if (message.type==='activity'){cursors.receive(message);return;}
      decoder=new WebCodecsVideoDecoder({codec:message.codec,renderer:new BitmapVideoFrameRenderer(canvas)});writer=decoder.writable.getWriter();
      decoder.sizeChanged(({width,height})=>{if ((canvas.width>canvas.height)!==(width>height)) {release();cursors.clear();}canvas.width=width;canvas.height=height;ready=true;fit();});
      status.textContent=settings.control?'Live · direct scrcpy input':'Live · read-only';return;
    }
    const view=new DataView(event.data),flag=view.getUint8(0),data=new Uint8Array(event.data,9);
    const packet=flag===0?{type:'configuration',data}:{type:'data',keyframe:flag===2,pts:view.getBigUint64(1),data};
    decoding=decoding.then(()=>writer.write(packet)).catch(e=>{status.textContent=e.message;socket.close();});
  };
  socket.onclose=()=>{release();cursors.clear();settings.control=false;control.close();enabled();recording?.stop();status.textContent='Video stopped. Check the claim, then reconnect.';};
  socket.onerror=()=>{status.textContent='Video connection failed.';};
  let lastFrames=0;
  setInterval(()=>{if (decoder){const frames=decoder.framesRendered;canvas.dataset.framesRendered=String(frames);$('video-stats').textContent=`${canvas.width} × ${canvas.height} · ${frames-lastFrames} fps (${settings.maxFps} cap)`;lastFrames=frames;}},1000);
} catch(e){status.textContent=e.message;}
