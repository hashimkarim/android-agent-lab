// Transport adapter only: Tango owns ADB/scrcpy, and WebCodecs owns decoding.
import {createServer} from 'node:http';
import {readFileSync} from 'node:fs';
import {spawn} from 'node:child_process';
import {timingSafeEqual, createHash} from 'node:crypto';
import {fileURLToPath} from 'node:url';
import {WebSocketServer, WebSocket} from 'ws';
import {AdbServerClient} from '@yume-chan/adb';
import {AdbServerNodeTcpConnector} from '@yume-chan/adb-server-node-tcp';
import {AdbScrcpyClient} from '@yume-chan/adb-scrcpy';
import {ReadableStream, WritableStream} from '@yume-chan/stream-extra';
import {mkdtemp, open, rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {LockBroker} from './broker.mjs';
import {LiveControl} from './control.mjs';
import {ViewerOptions} from './options.mjs';
import {desktopLibrary} from './library.mjs';

const config = JSON.parse(process.env.ADB_VIDEO_CONFIG);
const library = desktopLibrary(config);
const root = new URL('../', import.meta.url);
let client, controls, video, ending = false;
function owns() {
  try {
    const r = JSON.parse(readFileSync(config.record, 'utf8'));
    return r.token === config.token && r.server === config.server && r.expires_at * 1000 > Date.now();
  } catch { return false; }
}
function keyMatches(value) {
  const a = Buffer.from(value || ''), b = Buffer.from(config.key);
  return a.length === b.length && timingSafeEqual(a, b);
}
function localRequest(req) {
  const port = server.address().port;
  const hosts = [`127.0.0.1:${port}`, `localhost:${port}`];
  return hosts.includes(req.headers.host) && (!req.headers.origin || hosts.some(h => req.headers.origin === `http://${h}`));
}
function reply(res, code, data, type='application/json') {
  const body = Buffer.isBuffer(data) ? data : Buffer.from(JSON.stringify(data));
  res.writeHead(code, {'Content-Type': type, 'Cache-Control': 'no-store', 'Referrer-Policy': 'no-referrer',
    'X-Content-Type-Options': 'nosniff', 'Content-Security-Policy': "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self' ws://127.0.0.1:* ws://localhost:*; img-src 'self' blob:"});
  res.end(body);
}
let toolBusy = false;
async function jsonBody(req, limit=65536) {
  const chunks = []; let size = 0;
  for await (const chunk of req) {size += chunk.length;if (size > limit) throw new Error('Request too large');chunks.push(chunk);}
  return JSON.parse(Buffer.concat(chunks));
}
function deviceTool(data) {
  return new Promise((resolve, reject) => {
    const proc = spawn(config.python, [fileURLToPath(new URL('scripts/device_tools.py', root))], {env:process.env, stdio:['pipe','pipe','pipe']});
    let output = '', error = '';
    const timer = setTimeout(() => proc.kill(), data.tool === 'install' ? 190000 : 30000);
    proc.stdout.on('data', chunk => {output += chunk;if (output.length > 24000000) proc.kill();});
    proc.stderr.on('data', chunk => {error = (error + chunk).slice(-8000);});
    proc.once('error', e => {clearTimeout(timer);reject(e);});
    proc.once('close', code => {
      clearTimeout(timer);
      if (code !== 0) return reject(new Error(error.trim() || 'Developer tool stopped.'));
      try {resolve(JSON.parse(output));} catch {reject(new Error('Invalid developer tool response.'));}
    });
    proc.stdin.on('error', () => {}); proc.stdin.end(JSON.stringify(data));
  });
}
async function legacyInput(data) {
  const owner = Symbol('HTTP input'), actor = data.actor || 'human:browser';
  if (!['tap','swipe'].includes(data.kind)) return controls.submit(owner, {...data,actor});
  let {width,height} = config;
  if ((width > height) !== (video.width > video.height)) [width,height] = [height,width];
  const point = (x,y) => ({x:Math.round(x/width*(video.width-1)),y:Math.round(y/height*(video.height-1)),width:video.width,height:video.height});
  const first = point(data.x,data.y), last = data.kind === 'tap' ? first : point(data.x2,data.y2);
  const duration = data.kind === 'tap' ? 0 : data.duration ?? 300;
  if (!Number.isFinite(duration) || duration < 0 || duration > 10000) throw new Error('Swipe duration must be 0–10000 ms.');
  try {
    await controls.submit(owner, {kind:'pointer',phase:'down',actor,...first});
    const start = performance.now();
    while (performance.now() - start < duration) {
      await new Promise(r => setTimeout(r, 8));
      const t = Math.min(1,(performance.now()-start)/duration);
      await controls.submit(owner, {kind:'pointer',phase:'move',actor,...first,x:first.x+(last.x-first.x)*t,y:first.y+(last.y-first.y)*t});
    }
    await controls.submit(owner, {kind:'pointer',phase:'up',actor,...last});
  } finally { await controls.disconnect(owner); }
}
const server = createServer(async (req, res) => {
  if (!localRequest(req)) return reply(res, 403, {error:'Loopback origin required'});
  if (req.url === '/favicon.ico') {res.writeHead(204);return res.end();}
  const files = {'/':'index.html', '/client.js':'client.js', '/style.css':'style.css'};
  if (req.method === 'GET' && files[req.url]) {
    const type = req.url.endsWith('.js') ? 'text/javascript' : req.url.endsWith('.css') ? 'text/css' : 'text/html';
    return reply(res, 200, readFileSync(new URL(`public/${files[req.url]}`, import.meta.url)), type);
  }
  if (!keyMatches(req.headers['x-adb-preview-key'])) return reply(res, 403, {error:'Open the complete private viewer URL'});
  if (!owns()) return reply(res, 409, {error:'Device claim expired or changed'});
  if (req.method === 'GET' && req.url === '/status') return reply(res, 200, {serial:config.serial, control:config.control, width:config.width, height:config.height, maxFps:config.maxFps, profile:config.profile, controlTransport:'scrcpy'});
  if (req.url==='/library' || req.url==='/library/install' || req.url?.startsWith('/library/job/')) {
    if(!config.control) return reply(res,403,{error:'This viewer is read-only'});
    try {
      if(req.method==='GET' && req.url==='/library') return reply(res,200,await library.call({action:'catalog'}));
      if(req.method==='GET' && /^\/library\/job\/[a-zA-Z0-9-]+$/.test(req.url)) return reply(res,200,await library.call({action:'job',id:req.url.split('/').at(-1)}));
      if(req.method==='POST' && req.url==='/library/install' && req.headers['content-type']==='application/json') {
        const {kind,id,output}=await jsonBody(req,4096);
        return reply(res,200,await library.call({action:'install',kind,id,output}));
      }
      return reply(res,404,{error:'Unknown library route'});
    } catch(error) {return reply(res,409,{error:error.message});}
  }
  if (req.method !== 'POST' || !['/input','/devtools','/devtools/install'].includes(req.url)) return reply(res, 404, {error:'Unknown route'});
  if (!config.control) return reply(res, 403, {error:'This viewer is read-only'});
  if (req.url === '/input') {
    if (req.headers['content-type'] !== 'application/json') return reply(res,400,{error:'JSON required'});
    try {await legacyInput(await jsonBody(req));return reply(res,200,{ok:true});}
    catch (error) {return reply(res,409,{error:error.message});}
  }
  if (toolBusy) return reply(res,409,{error:'Another developer tool is running.'});
  toolBusy = true; let directory;
  try {
    let data;
    if (req.url === '/devtools/install') {
      if (req.headers['content-type'] !== 'application/vnd.android.package-archive') throw new Error('Choose an APK file.');
      directory = await mkdtemp(join(tmpdir(),'android-agent-lab-'));
      const path = join(directory,'upload.apk'), file = await open(path,'wx',0o600);
      try {
        let size = 0;
        for await (const chunk of req) {size += chunk.length;if (size > 200*1024*1024) throw new Error('APK exceeds 200 MB. Use the coordinated CLI for larger APKs.');await file.writeFile(chunk);}
        if (!size) throw new Error('The APK is empty.');
      } finally {await file.close();}
      data = {tool:'install',path};
    } else {
      if (req.headers['content-type'] !== 'application/json') throw new Error('JSON required');
      const body = await jsonBody(req,4096);
      if (!['logcat','hierarchy','settings','developer-options','app-settings','screenshot','rotate','auto-rotate'].includes(body.tool)) throw new Error('Unknown developer tool');
      data = {tool:body.tool};
      if (body.tool === 'rotate') data.rotation = video.width > video.height ? 0 : 1;
    }
    reply(res,200,await deviceTool(data));
  } catch (error) { reply(res,409,{error:error.message}); }
  finally { toolBusy = false;if (directory) await rm(directory,{recursive:true,force:true}); }
});
server.requestTimeout = 60000;
server.headersTimeout = 5000;
const wss = new WebSocketServer({noServer:true, maxPayload:4096, perMessageDeflate:false});
const inputWss = new WebSocketServer({noServer:true, maxPayload:65536, perMessageDeflate:false});
server.on('upgrade', (req, socket, head) => {
  const protocol = req.headers['sec-websocket-protocol'];
  const input = req.url === '/control', prefix = input ? /^adb-control\./ : /^adb-video\./;
  if (!['/stream','/control'].includes(req.url) || !localRequest(req) || !owns() || !keyMatches(typeof protocol === 'string' ? protocol.replace(prefix, '') : '')) return socket.destroy();
  const target = input ? inputWss : wss;
  socket.setNoDelay(true);
  target.handleUpgrade(req, socket, head, ws => target.emit('connection', ws));
});
inputWss.on('connection', ws => {
  ws.on('message', (buffer,isBinary) => {
    let data;
    try {if (isBinary) throw new Error('JSON required');data=JSON.parse(buffer);if (!data || typeof data !== 'object') throw new Error('JSON object required');}
    catch {ws.close(1003,'Invalid control message');return;}
    controls.submit(ws,data).then(() => {
      if (data.id && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify({type:'input-result',id:data.id,ok:true}));
    }).catch(error => {
      if (ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify({type:'input-result',id:data.id,ok:false,error:error.message}));
    });
  });
  ws.on('close', () => controls.disconnect(ws).catch(() => {}));
});
let metadata, configuration, group = [], groupSize = 0, groupValid = false;
const activitySession = createHash('sha256').update(config.token).digest('hex');
const seenActivity = new Set();
let recentActivity = [];
function sendActivity(ws, events) {
  if (events.length && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify({type:'activity', events, now:Date.now()}));
}
setInterval(() => {
  if (!owns()) return;
  try {
    const state = JSON.parse(readFileSync(config.activity, 'utf8'));
    if (state.session !== activitySession || !Array.isArray(state.events)) return;
    recentActivity = state.events.filter(e => typeof e.at === 'number' && e.at * 1000 > Date.now() - 8000).slice(-32);
    const fresh = recentActivity.filter(e => !seenActivity.has(`${e.id}:${e.phase}`));
    for (const e of fresh) seenActivity.add(`${e.id}:${e.phase}`);
    if (seenActivity.size > 128) {
      seenActivity.clear();
      for (const e of recentActivity) seenActivity.add(`${e.id}:${e.phase}`);
    }
    for (const ws of wss.clients) sendActivity(ws, fresh);
  } catch { /* Feedback is optional; video keeps streaming without an activity file. */ }
}, 75).unref();
wss.on('connection', ws => {
  ws.send(JSON.stringify(metadata));
  if (configuration) ws.send(configuration);
  if (groupValid) for (const frame of group) ws.send(frame);
  sendActivity(ws, recentActivity.filter(e => e.at * 1000 > Date.now() - 8000));
  sendActivity(ws, [...controls.presence.values()].map(e => ({...e,phase:'hover',at:Date.now()/1000})));
});
async function stop(code=0) {
  if (ending) return;
  ending = true;
  for (const ws of wss.clients) ws.close(1000, 'Viewer stopped or device handed off');
  for (const ws of inputWss.clients) ws.close(1000, 'Viewer stopped or device handed off');
  server.close();
  const timeout = setTimeout(() => process.exit(code), 2000);
  try { await controls?.close(); await client?.close(); } finally { clearTimeout(timeout); process.exit(code); }
}
process.on('SIGTERM', () => void stop());
process.on('SIGINT', () => void stop());
setInterval(() => {if (!owns() || process.ppid !== config.supervisor) void stop();}, 250).unref();
try {
  if (!owns()) throw new Error('Device claim is no longer valid');
  const adb = await new AdbServerClient(new AdbServerNodeTcpConnector(config.endpoint)).createAdb({serial:config.serial});
  const remote = `/data/local/tmp/android-agent-lab-scrcpy-${process.pid}.jar`;
  const jar = readFileSync(config.serverFile);
  await AdbScrcpyClient.pushServer(adb, new ReadableStream({start(c) {c.enqueue(jar);c.close();}}), remote);
  client = await AdbScrcpyClient.start(adb, remote, new ViewerOptions({audio:false, control:config.control, clipboardAutosync:false,
    maxSize:config.maxSize, maxFps:config.maxFps, videoBitRate:config.bitRate || 4_000_000,
    videoCodecOptions:'i-frame-interval:float=0.25', tunnelForward:true}));
  client.output.pipeTo(new WritableStream({write(line) {process.stderr.write(`[scrcpy] ${line}\n`);}})).catch(() => {});
  client.exited.then(() => stop()).catch(() => stop(1));
  video = await client.videoStream;
  const broker = config.control ? new LockBroker(config, fileURLToPath(new URL('scripts/control_broker.py',root)), () => void stop(1)) : null;
  controls = new LiveControl({controller:client.controller, broker, owns, size:()=>({width:video.width,height:video.height}), physicalSize:()=>config,
    broadcast:message => {
      // The broker persists the same gesture for CLI observers. Do not replay its
      // delayed start/end records over newer live movement in connected viewers.
      for (const event of message.events) {
        if (['down','start'].includes(event.phase)) seenActivity.add(`${event.id}:start`);
        if (['up','cancel','complete'].includes(event.phase)) seenActivity.add(`${event.id}:complete`);
      }
      for (const ws of wss.clients) if (ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify(message));
    }});
  video.sizeChanged(() => {if (controls.active) controls.disconnect(controls.active.owner).catch(() => {});});
  metadata = {type:'video', codec:video.metadata.codec};
  await new Promise(resolve => server.listen(config.port, '127.0.0.1', resolve));
  process.stdout.write(JSON.stringify({url:`http://127.0.0.1:${server.address().port}/#key=${config.key}`, serial:config.serial, control:config.control})+'\n');
  await video.stream.pipeTo(new WritableStream({write(packet) {
    const header = Buffer.alloc(9);
    header[0] = packet.type === 'configuration' ? 0 : packet.keyframe ? 2 : 1;
    header.writeBigUint64BE(packet.pts ?? 0n, 1);
    const frame = Buffer.concat([header, packet.data]);
    if (packet.type === 'configuration') {configuration = frame;group = [];groupSize = 0;groupValid = false;}
    else {
      if (packet.keyframe) {group = [];groupSize = 0;groupValid = true;}
      if (groupValid && groupSize + frame.length <= 8_000_000) {group.push(frame);groupSize += frame.length;}
      else {group = [];groupSize = 0;groupValid = false;}
    }
    for (const ws of wss.clients) {
      if (ws.bufferedAmount > 1_000_000) ws.close(1013, 'Viewer cannot keep up; lower max-size/FPS');
      else if (ws.readyState === WebSocket.OPEN) ws.send(frame);
    }
  }}));
} catch (error) {process.stderr.write(`${error.stack || error}\n`);await stop(1);}
