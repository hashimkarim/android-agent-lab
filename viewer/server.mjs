// Transport adapter only: Tango owns ADB/scrcpy, and WebCodecs owns decoding.
import {createServer} from 'node:http';
import {readFileSync} from 'node:fs';
import {spawn} from 'node:child_process';
import {timingSafeEqual} from 'node:crypto';
import {fileURLToPath} from 'node:url';
import {WebSocketServer, WebSocket} from 'ws';
import {AdbServerClient} from '@yume-chan/adb';
import {AdbServerNodeTcpConnector} from '@yume-chan/adb-server-node-tcp';
import {AdbScrcpyClient, AdbScrcpyOptions3_3_3} from '@yume-chan/adb-scrcpy';
import {ReadableStream, WritableStream} from '@yume-chan/stream-extra';

const config = JSON.parse(process.env.ADB_VIDEO_CONFIG);
const root = new URL('../', import.meta.url);
let client, ending = false;
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
let inputBusy = false;
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
  if (req.method === 'GET' && req.url === '/status') return reply(res, 200, {serial:config.serial, control:config.control, width:config.width, height:config.height, maxFps:config.maxFps});
  if (req.method !== 'POST' || req.url !== '/input') return reply(res, 404, {error:'Unknown route'});
  if (!config.control) return reply(res, 403, {error:'This viewer is read-only'});
  if (inputBusy) return reply(res, 409, {error:'Input in progress; retry when it finishes'});
  if (req.headers['content-type'] !== 'application/json') return reply(res, 400, {error:'JSON required'});
  inputBusy = true;
  try {
    const chunks = []; let size = 0;
    for await (const chunk of req) {
      size += chunk.length;
      if (size > 4096) { reply(res, 413, {error:'Input too large'}); return; }
      chunks.push(chunk);
    }
    const data = Buffer.concat(chunks);
    const result = await new Promise((resolve, reject) => {
      const proc = spawn(config.python, [fileURLToPath(new URL('scripts/video.py', root)), 'rpc'], {env:process.env, stdio:['pipe','pipe','pipe']});
      let error = '';
      proc.stderr.on('data', chunk => error += chunk);
      proc.on('error', reject);
      proc.on('exit', code => resolve({code, error}));
      proc.stdin.end(data);
    });
    reply(res, result.code === 0 ? 200 : 409, result.code === 0 ? {ok:true} : {error:result.error.trim()});
  } catch (error) { reply(res, 400, {error:error.message}); }
  finally { inputBusy = false; }
});
server.requestTimeout = 5000;
server.headersTimeout = 5000;
const wss = new WebSocketServer({noServer:true, maxPayload:4096, perMessageDeflate:false});
server.on('upgrade', (req, socket, head) => {
  const protocol = req.headers['sec-websocket-protocol'];
  if (req.url !== '/stream' || !localRequest(req) || !owns() || !keyMatches(typeof protocol === 'string' ? protocol.replace(/^adb-video\./, '') : '')) return socket.destroy();
  wss.handleUpgrade(req, socket, head, ws => wss.emit('connection', ws));
});
let metadata, configuration, group = [], groupSize = 0, groupValid = false;
wss.on('connection', ws => {
  ws.send(JSON.stringify(metadata));
  if (configuration) ws.send(configuration);
  if (groupValid) for (const frame of group) ws.send(frame);
});
async function stop(code=0) {
  if (ending) return;
  ending = true;
  for (const ws of wss.clients) ws.close(1000, 'Viewer stopped or device handed off');
  server.close();
  const timeout = setTimeout(() => process.exit(code), 2000);
  try { await client?.close(); } finally { clearTimeout(timeout); process.exit(code); }
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
  client = await AdbScrcpyClient.start(adb, remote, new AdbScrcpyOptions3_3_3({audio:false, control:false,
    maxSize:config.maxSize, maxFps:config.maxFps, videoBitRate:4_000_000,
    videoCodecOptions:'i-frame-interval=1', tunnelForward:true}));
  client.output.pipeTo(new WritableStream({write(line) {process.stderr.write(`[scrcpy] ${line}\n`);}})).catch(() => {});
  client.exited.then(() => stop()).catch(() => stop(1));
  const video = await client.videoStream;
  metadata = {codec:video.metadata.codec};
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
