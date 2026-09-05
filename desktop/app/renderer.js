'use strict';
const $ = id => document.getElementById(id);
let claimDevice;
let refreshing = false;
function notice(message, error = false) {
  $('notice').textContent = message;
  $('notice').className = error ? 'error' : '';
  $('notice').hidden = !message;
}
async function request(action, data = {}, button) {
  if (button) button.disabled = true;
  try {
    const result = await window.lab.request(action, data);
    if (result.message) notice(result.message);
    return result;
  } catch (error) { notice(error.message.replace(/^Error invoking remote method '[^']+': Error: /, ''), true); }
  finally { if (button?.isConnected) button.disabled = false; }
}
function element(tag, text, className) {
  const node = document.createElement(tag);
  if (text) node.textContent = text;
  if (className) node.className = className;
  return node;
}
function button(text, action, className = 'quiet') {
  const node = element('button', text, className);
  node.addEventListener('click', () => action(node));
  return node;
}
async function openDevice(device, token, target) {
  notice('Starting the shared viewer…');
  const result = await request('start', {serial: device.serial, token, reclaim: device.claim?.expired === true, port: Number($('port').value)}, target);
  if (result) notice('Device open. Copy its browser URL or agent instructions below to share this session.');
  await refresh();
}
function renderDevices(devices) {
  $('devices').replaceChildren();
  if (!devices.length) $('devices').append(element('p', 'No devices connected. Plug in a phone with USB debugging enabled, or start the emulator below.', 'empty'));
  for (const device of devices) {
    const card = element('article', '', 'device');
    card.append(element('span', device.state === 'device' ? 'Connected' : device.state, 'badge' + (device.state === 'device' ? '' : ' offline')),
      element('h3', device.model), element('p', device.serial, 'serial'));
    const claimed = device.claim && !device.claim.expired;
    card.append(element('p', claimed ? `In use by ${device.claim.owner}` : device.claim ? `Expired claim · ${device.claim.owner}` : 'Available for a shared session', 'ownership'));
    const open = button(claimed ? 'Join with owner’s token' : device.claim ? 'Reclaim expired session' : 'Open device', target => {
      if (claimed) {
        claimDevice = device;
        $('claim-description').textContent = `${device.model} is claimed by ${device.claim.owner}. Use their token to share the device.`;
        $('claim-token').value = '';
        $('claim-dialog').showModal();
      } else openDevice(device, undefined, target);
    }, '');
    open.disabled = device.state !== 'device';
    card.append(open);
    if (device.state === 'unauthorized') card.append(element('p', 'Unlock the phone and accept its USB debugging prompt.', 'fine'));
    $('devices').append(card);
  }
}
function renderSessions(sessions) {
  $('sessions-section').hidden = !sessions.length;
  $('sessions').replaceChildren();
  for (const session of sessions) {
    const card = element('article', '', 'session');
    card.append(element('h3', session.serial), element('p', session.status));
    const actions = element('div', '', 'session-actions');
    for (const [text, action] of [['Open window', 'reopen'], ['Copy browser URL', 'copyUrl'], ['Copy agent instructions', 'copyAgent'], ['Stop session', 'stop']]) {
      const control = button(text, target => request(action, {id: session.id}, target), action === 'stop' ? 'danger' : 'quiet');
      control.disabled = !session.status.startsWith('Live');
      actions.append(control);
    }
    card.append(actions, element('p', session.owned ? 'Stopping releases this app’s claim. The emulator keeps running.' : 'Using the owner’s token. Stopping leaves their claim intact.', 'fine'));
    $('sessions').append(card);
  }
}
function update(value) {
  renderSessions(value.sessions);
  $('emulator').disabled = value.emulatorRunning;
  $('emulator').textContent = value.emulatorRunning ? 'Starting Android…' : 'Start emulator';
  $('log').textContent = value.emulatorLog || 'No emulator startup in progress.';
  $('log').scrollTop = $('log').scrollHeight;
  if (value.message) { notice(value.message); refresh(); }
}
async function refresh() {
  if (refreshing) return;
  refreshing = true;
  try {
    const status = await request('status', {}, $('refresh'));
    if (!status) { $('requirements').textContent = 'Python 3.10+ and ADB are needed to start device sessions. You can still open an existing viewer URL.'; return; }
    $('requirements').textContent = `Python ${status.python} · ${status.adb ? 'ADB ready' : 'ADB missing'} · ${status.server}`;
    $('version').textContent = `Android Agent Lab ${status.version}`;
    if (status.error) notice(status.error, true);
    renderDevices(status.devices);
    update(status);
    const capable = status.architecture === 'x86_64' && status.kvm && status.docker;
    $('emulator').disabled = status.emulatorRunning || !capable;
    if (!capable) $('emulator-help').textContent = 'Local emulator needs Linux x86_64, Docker Compose and read/write access to /dev/kvm. Physical phones work independently.';
  } finally { refreshing = false; }
}
$('refresh').addEventListener('click', refresh);
for (const [id, action] of [['docs', 'docs'], ['skill', 'installSkill'], ['emulator', 'emulator']]) $(id).addEventListener('click', () => request(action, {}, $(id)));
$('join-form').addEventListener('submit', async event => {
  event.preventDefault();
  if (await request('open', {url: $('join-url').value.trim()}, event.submitter)) { $('join-url').value = ''; notice('Shared viewer opened in a desktop window.'); }
});
$('cancel-claim').addEventListener('click', () => $('claim-dialog').close());
$('claim-form').addEventListener('submit', async event => {
  event.preventDefault();
  const token = $('claim-token').value.trim();
  $('claim-token').value = '';
  $('claim-dialog').close();
  await openDevice(claimDevice, token);
});
window.lab.onUpdate(update);
refresh();
