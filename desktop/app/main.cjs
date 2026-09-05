'use strict';
const {app, BrowserWindow, ipcMain, clipboard, shell} = require('electron');
const {spawn, execFile} = require('node:child_process');
const fs = require('node:fs');
const path = require('node:path');
const os = require('node:os');
const crypto = require('node:crypto');
const {pathToFileURL} = require('node:url');
const {viewerUrl, portNumber, agentInstructions} = require('./core.cjs');

app.setName('android-agent-lab');
if (process.env.ADB_LAB_USER_DATA) app.setPath('userData', process.env.ADB_LAB_USER_DATA);
const smoke = process.argv.includes('--smoke-test');
const runtime = app.isPackaged ? path.join(process.resourcesPath, 'runtime') : path.resolve(__dirname, '../../.desktop-build/runtime');
const dataHome = app.getPath('userData');
const labHome = path.join(dataHome, 'lab');
const skillHome = path.join(dataHome, 'skills/adb-coordination');
const python = process.env.ADB_LAB_PYTHON || 'python3';
const sessions = new Map();
const viewers = new Set();
const starting = new Set();
let manager, emulator, quitting = false;
let emulatorLog = '';

function environment() {
  const env = {...process.env, ADB_LAB_HOME: labHome,
    ADB_VIDEO_SERVER: path.join(runtime, 'vendor/scrcpy-server-v3.3.3'),
    ADB_VIDEO_NODE: process.execPath, ADB_VIDEO_ELECTRON_NODE: '1'};
  delete env.ELECTRON_RUN_AS_NODE;
  return env;
}

function rpc(data) {
  return new Promise((resolve, reject) => {
    const child = execFile(python, [path.join(runtime, 'scripts/desktop_rpc.py')],
      {env: environment(), timeout: 20000, maxBuffer: 1024 * 1024}, (error, stdout, stderr) => {
        if (error) return reject(new Error(stderr.trim() || `Install Python 3.10+ and Android platform-tools (adb). ${error.message}`));
        try { resolve(JSON.parse(stdout)); } catch { reject(new Error('Invalid response from the device coordinator.')); }
      });
    child.stdin.on('error', () => {});
    child.stdin.end(JSON.stringify(data));
  });
}

function snapshot() {
  return {sessions: [...sessions.values()].map(s => ({id: s.id, serial: s.serial, status: s.status, owned: s.owned})),
    emulatorRunning: Boolean(emulator), emulatorLog};
}
function update(extra = {}) {
  if (manager && !manager.isDestroyed()) manager.webContents.send('lab:update', {...snapshot(), ...extra});
}

function lockWindow(window, allowed) {
  window.webContents.setWindowOpenHandler(() => ({action: 'deny'}));
  window.webContents.on('will-navigate', (event, target) => { if (!allowed(target)) event.preventDefault(); });
  window.webContents.on('will-redirect', (event, target) => { if (!allowed(target)) event.preventDefault(); });
  window.webContents.session.setPermissionRequestHandler((_wc, _permission, callback) => callback(false));
  window.webContents.session.setPermissionCheckHandler(() => false);
}

async function openViewer(value, title = 'Shared device') {
  const url = viewerUrl(value);
  const window = new BrowserWindow({width: 720, height: 1000, minWidth: 430, minHeight: 520,
    title: `${title} — Android Agent Lab`, backgroundColor: '#0b1020',
    icon: path.join(__dirname, 'icon.png'), autoHideMenuBar: true,
    webPreferences: {nodeIntegration: false, contextIsolation: true, sandbox: true}});
  viewers.add(window);
  window.on('closed', () => viewers.delete(window));
  lockWindow(window, value => { try { return new URL(value).origin === url.origin; } catch { return false; } });
  await window.loadURL(url.href);
  return {ok: true};
}

async function startSession(data) {
  if (typeof data.serial !== 'string' || !data.serial || data.serial.startsWith('-') || data.serial.length > 512) throw new Error('Choose an online device.');
  if (starting.has(data.serial) || [...sessions.values()].some(s => s.serial === data.serial)) throw new Error('This device already has a desktop session.');
  const port = portNumber(data.port);
  starting.add(data.serial);
  let token, owned = false, child;
  try {
    if (data.token) {
      if (typeof data.token !== 'string' || data.token.length > 128) throw new Error('Invalid claim token.');
      token = data.token;
      await rpc({action: 'check', serial: data.serial, token});
    } else {
      const record = await rpc({action: 'claim', serial: data.serial, owner: `human:desktop:${crypto.randomUUID().slice(0, 8)}`, reclaim: data.reclaim === true});
      token = record.token; owned = true;
    }
    if (quitting) throw new Error('Application is closing.');
    const id = crypto.randomUUID();
    const args = [path.join(runtime, 'scripts/video.py'), 'start', '--serial', data.serial, '--control',
      '--port', String(port), '--duration', '86400', '--parent-pid', String(process.pid)];
    if (owned) args.push('--release-on-exit');
    child = spawn(python, args, {env: {...environment(), ADB_COORD_TOKEN: token}, stdio: ['ignore', 'pipe', 'pipe']});
    const session = {id, serial: data.serial, token, owned, child, status: 'Starting…'};
    sessions.set(id, session);
    update();
    let errors = '';
    child.stderr.on('data', chunk => { errors = (errors + chunk.toString()).slice(-8000); });
    child.on('close', () => {
      sessions.delete(id);
      update(errors ? {message: `Session ended: ${errors.trim()}`} : {message: 'Device session ended.'});
    });
    const info = await new Promise((resolve, reject) => {
      let buffer = '';
      const timer = setTimeout(() => reject(new Error('Viewer startup timed out.')), 60000);
      const finish = (error, info) => { clearTimeout(timer); error ? reject(error) : resolve(info); };
      child.once('error', error => { sessions.delete(id); finish(error); });
      child.once('close', () => finish(new Error(errors.trim() || 'Viewer stopped during startup.')));
      child.stdout.on('data', chunk => {
        buffer += chunk.toString();
        if (buffer.length > 65536) return finish(new Error('Invalid viewer startup response.'));
        if (!buffer.includes('\n')) return;
        try { finish(null, JSON.parse(buffer.split('\n')[0])); } catch { finish(new Error('Invalid viewer startup response.')); }
      });
    });
    session.url = viewerUrl(info.url).href;
    session.status = 'Live · shared with browser and agents';
    update();
    if (!quitting) await openViewer(session.url, data.serial);
    return {ok: true};
  } catch (error) {
    if (child && child.exitCode === null) child.kill('SIGTERM');
    // Also covers errors before the supervisor took responsibility for the claim.
    if (owned) await rpc({action: 'release', serial: data.serial, token}).catch(() => {});
    throw error;
  } finally { starting.delete(data.serial); }
}

function stopSession(session) {
  if (!session) throw new Error('Session has already ended.');
  session.status = 'Stopping…';
  session.child.kill('SIGTERM');
  update();
}

function startEmulator() {
  if (emulator) throw new Error('Emulator startup is already running.');
  if (process.arch !== 'x64') throw new Error('The bundled Android 16 Docker emulator requires Linux x86_64. ARM64 supports physical devices and remote ADB.');
  emulatorLog = 'Starting Android 16. The first build downloads several GB and may take 15 minutes.\n';
  emulator = spawn(python, ['-u', path.join(runtime, 'scripts/lab.py'), 'up', '--timeout', '600'], {env: environment(), stdio: ['ignore', 'pipe', 'pipe']});
  const output = chunk => { emulatorLog = (emulatorLog + chunk.toString()).slice(-12000); update(); };
  emulator.stdout.on('data', output); emulator.stderr.on('data', output);
  emulator.on('error', error => { emulatorLog += error.message; });
  emulator.on('close', code => { emulator = null; update({message: code === 0 ? 'Android is ready. Refresh devices to open it.' : 'Emulator startup did not finish. See the startup log.'}); });
  update();
  return {ok: true};
}

function installSkill() {
  const results = [];
  for (const client of ['.codex', '.claude', '.agents']) {
    const destination = path.join(os.homedir(), client, 'skills/adb-coordination');
    fs.mkdirSync(path.dirname(destination), {recursive: true});
    try { fs.symlinkSync(skillHome, destination, 'dir'); results.push(`${client}: installed`); }
    catch (error) { if (error.code === 'EEXIST') results.push(`${client}: existing skill kept`); else throw error; }
  }
  return {message: results.join(' · ') + '. Refresh your agent session.'};
}

const actions = {
  status: async () => ({...await rpc({action: 'status'}), ...snapshot(), version: app.getVersion(), skillHome}),
  start: startSession,
  open: data => openViewer(data.url),
  reopen: data => openViewer(requiredSession(data.id).url, requiredSession(data.id).serial),
  stop: data => { stopSession(requiredSession(data.id)); return {ok: true}; },
  copyUrl: data => { clipboard.writeText(requiredSession(data.id).url); return {message: 'Private browser URL copied.'}; },
  copyAgent: data => {
    const session = requiredSession(data.id);
    const state = process.env.ADB_COORD_STATE || path.join(process.env.XDG_STATE_HOME || path.join(os.homedir(), '.local/state'), 'adb-coordination');
    clipboard.writeText(agentInstructions({...session, python, skill: skillHome, server: process.env.ADB_SERVER_SOCKET, state}));
    return {message: 'Private agent instructions copied. Paste into your Codex, Claude, or T3 thread.'};
  },
  emulator: startEmulator,
  installSkill,
  docs: () => { shell.openExternal('https://github.com/Hashim-K/android-agent-lab/blob/main/docs/desktop.md'); return {ok: true}; },
};
function requiredSession(id) { const s = sessions.get(id); if (!s || !s.url) throw new Error('This session is not ready or has ended.'); return s; }

function prepareData() {
  for (const name of ['scripts/video.py', 'viewer/server.mjs', 'viewer/public/client.js', 'vendor/scrcpy-server-v3.3.3']) {
    if (!fs.existsSync(path.join(runtime, name))) throw new Error('Desktop runtime missing. From source, run npm run prepare-runtime --prefix desktop.');
  }
  fs.mkdirSync(labHome, {recursive: true, mode: 0o700});
  for (const name of ['Dockerfile', 'compose.yaml', '.dockerignore']) fs.copyFileSync(path.join(runtime, name), path.join(labHome, name));
  fs.cpSync(path.join(runtime, 'skills/adb-coordination'), skillHome, {recursive: true});
}

async function smokeTest() {
  const frontend = await manager.webContents.executeJavaScript(`({bridge: typeof window.lab?.request === 'function', node: typeof process, decoder: typeof VideoDecoder, title: document.title})`);
  const codec = await manager.webContents.executeJavaScript(`VideoDecoder.isConfigSupported({codec:'avc1.42E01E',codedWidth:720,codedHeight:1280}).then(x=>x.supported)`);
  const bundledNode = await new Promise((resolve, reject) => execFile(process.execPath, ['-e', 'process.stdout.write(process.versions.node)'],
    {env: {...process.env, ELECTRON_RUN_AS_NODE: '1'}}, (e, out) => e ? reject(e) : resolve(out)));
  const pythonVersion = await new Promise((resolve, reject) => execFile(python, ['-c', 'import sys; assert sys.version_info >= (3, 10); print(sys.version.split()[0])'],
    (e, out) => e ? reject(e) : resolve(out.trim())));
  if (!frontend.bridge || frontend.node !== 'undefined' || !codec) throw new Error('Desktop isolation or H.264 decoding check failed.');
  console.log(JSON.stringify({smoke: 'passed', version: app.getVersion(), architecture: process.arch, frontend, codec, bundledNode, python: pythonVersion}));
  app.quit();
}

if (!smoke && !app.requestSingleInstanceLock()) app.quit();
else {
  app.on('second-instance', () => { if (manager) { manager.restore(); manager.show(); manager.focus(); } });
  app.whenReady().then(async () => {
    prepareData();
    manager = new BrowserWindow({width: 1120, height: 830, minWidth: 800, minHeight: 620,
      show: !smoke, title: 'Android Agent Lab', icon: path.join(__dirname, 'icon.png'),
      backgroundColor: '#0b1020', autoHideMenuBar: true,
      webPreferences: {preload: path.join(__dirname, 'preload.cjs'), nodeIntegration: false, contextIsolation: true, sandbox: true}});
    const page = pathToFileURL(path.join(__dirname, 'index.html')).href;
    lockWindow(manager, url => url === page);
    ipcMain.handle('lab:request', async (event, action, data = {}) => {
      if (event.sender !== manager.webContents || event.senderFrame !== manager.webContents.mainFrame || event.senderFrame.url !== page) throw new Error('Untrusted desktop request.');
      if (!Object.hasOwn(actions, action) || !data || typeof data !== 'object') throw new Error('Unknown desktop request.');
      return actions[action](data);
    });
    manager.on('closed', () => app.quit());
    await manager.loadURL(page);
    if (smoke) await smokeTest();
  }).catch(error => { console.error(error); if (!smoke) require('electron').dialog.showErrorBox('Android Agent Lab', error.message); app.exit(1); });
}

app.on('before-quit', event => {
  if (quitting || sessions.size === 0 && !emulator && starting.size === 0) return;
  event.preventDefault(); quitting = true;
  for (const window of viewers) window.close();
  if (emulator) emulator.kill('SIGTERM');
  const children = [...sessions.values()].map(s => s.child);
  for (const child of children) child.kill('SIGTERM');
  Promise.race([
    Promise.all([
      ...children.map(child => new Promise(resolve => child.exitCode !== null ? resolve() : child.once('close', resolve))),
      new Promise(resolve => {
        if (!starting.size) return resolve();
        const timer = setInterval(() => { if (!starting.size) { clearInterval(timer); resolve(); } }, 100);
        timer.unref();
      }),
    ]),
    new Promise(resolve => setTimeout(resolve, 25000)),
  ]).finally(() => app.quit());
});
