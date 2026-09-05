import {WebCodecsVideoDecoder, BitmapVideoFrameRenderer} from '@yume-chan/scrcpy-decoder-webcodecs';
// Opening a new session URL in the same tab may only change its fragment.
window.addEventListener('hashchange', () => location.reload());
const key = new URLSearchParams(location.hash.slice(1)).get('key');
const canvas = document.querySelector('#screen'), status = document.querySelector('#status');
let decoder, writer, settings, socket, startPoint, inputQueue = Promise.resolve(), queued = 0;
async function api(path, data) {
  const response = await fetch(path, {method:data ? 'POST':'GET', headers:{'X-ADB-Preview-Key':key || '', ...(data ? {'Content-Type':'application/json'}:{})}, ...(data ? {body:JSON.stringify(data)}:{})});
  const result = await response.json();
  if (!response.ok) throw new Error(result.error);
  return result;
}
function send(data) {
  if (!settings?.control) return Promise.resolve(false);
  if (queued >= 20) {status.textContent='Input queue is full; wait before sending more.';return Promise.resolve(false);}
  queued++;
  const result = inputQueue.then(() => api('/input', data));
  inputQueue = result.catch(e => status.textContent=e.message).finally(() => queued--);
  return result.then(() => true, () => false);
}
function point(event) {
  const r = canvas.getBoundingClientRect();
  let {width, height} = settings;
  if ((canvas.width > canvas.height) !== (width > height)) [width,height] = [height,width];
  return {x:Math.max(0,Math.min(width-1,Math.round((event.clientX-r.left)/r.width*width))),
    y:Math.max(0,Math.min(height-1,Math.round((event.clientY-r.top)/r.height*height)))};
}
canvas.onpointerdown = e => {if (settings?.control) {canvas.focus();startPoint=point(e);canvas.setPointerCapture(e.pointerId);}};
canvas.onpointercancel = () => startPoint=null;
canvas.onpointerup = e => {
  if (!startPoint) return;
  const first=startPoint, end=point(e);startPoint=null;
  send(Math.hypot(first.x-end.x, first.y-end.y)>15 ? {kind:'swipe',...first,x2:end.x,y2:end.y}:{kind:'tap',...end});
};
canvas.onkeydown = e => {
  const keys={Backspace:'DEL',Enter:'ENTER',Tab:'TAB',Escape:'BACK',ArrowLeft:'DPAD_LEFT',ArrowRight:'DPAD_RIGHT',ArrowUp:'DPAD_UP',ArrowDown:'DPAD_DOWN'};
  if (e.ctrlKey || e.metaKey || e.altKey) return;
  if (keys[e.key]) {e.preventDefault();send({kind:'key',key:keys[e.key]});}
  else if (e.key.length===1) {e.preventDefault();send({kind:'text',text:e.key});}
};
document.querySelectorAll('[data-key]').forEach(b => b.onclick=() => send({kind:'key',key:b.dataset.key}));
document.querySelector('#text-form').onsubmit = async e => {
  e.preventDefault();const input=document.querySelector('#text'), value=input.value;
  if (value && await send({kind:'text',text:value}) && input.value===value) input.value='';
};
document.querySelector('#reload').onclick = () => location.reload();
try {
  if (!WebCodecsVideoDecoder.isSupported) throw new Error('This browser lacks WebCodecs. Use a current Chromium browser or the noVNC fallback.');
  settings = await api('/status');
  document.querySelector('#device').textContent=settings.serial;
  document.querySelectorAll('[data-key], #text-form input, #text-form button').forEach(e => e.disabled=!settings.control);
  socket = new WebSocket(`${location.protocol==='https:'?'wss':'ws'}://${location.host}/stream`, `adb-video.${key}`);
  socket.binaryType='arraybuffer';
  let decoding = Promise.resolve();
  socket.onmessage = event => {
    if (typeof event.data==='string') {
      decoder = new WebCodecsVideoDecoder({codec:JSON.parse(event.data).codec, renderer:new BitmapVideoFrameRenderer(canvas)});
      writer=decoder.writable.getWriter();
      decoder.sizeChanged(({width,height}) => {canvas.width=width;canvas.height=height;});
      status.textContent=settings.control ? 'Live video · click the screen to focus keyboard input' : 'Live video · read-only';
      return;
    }
    const view = new DataView(event.data), flag=view.getUint8(0), data=new Uint8Array(event.data,9);
    const packet=flag===0 ? {type:'configuration',data}:{type:'data',keyframe:flag===2,pts:view.getBigUint64(1),data};
    decoding=decoding.then(() => writer.write(packet)).catch(e => {status.textContent=e.message;socket.close();});
  };
  socket.onclose = () => {
    settings.control=false;
    document.querySelectorAll('[data-key], #text-form input, #text-form button').forEach(e => e.disabled=true);
    status.textContent='Video stopped. Check the device claim, then reconnect.';
  };
  socket.onerror = () => {status.textContent='Video connection failed.';};
  setInterval(() => {if (decoder) canvas.dataset.framesRendered=String(decoder.framesRendered);}, 500);
} catch (e) {status.textContent=e.message;}
