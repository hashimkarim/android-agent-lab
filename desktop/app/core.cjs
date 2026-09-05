'use strict';

function viewerUrl(value) {
  const url = new URL(value);
  if (url.protocol !== 'http:' || !['127.0.0.1', 'localhost', '[::1]'].includes(url.hostname) ||
      url.username || url.password || url.pathname !== '/' || url.search ||
      !/^[\w-]{32,128}$/.test(new URLSearchParams(url.hash.slice(1)).get('key') || '')) {
    throw new Error('Paste a private Android Agent Lab viewer URL on localhost. Use an SSH tunnel for another host.');
  }
  return url;
}

function portNumber(value) {
  if (!Number.isInteger(value) || value < 0 || value > 65535 || (value > 0 && value < 1024)) {
    throw new Error('Use port 0 for automatic selection, or a port from 1024 to 65535.');
  }
  return value;
}

function shellQuote(value) { return "'" + String(value).replaceAll("'", "'\\''") + "'"; }

function agentInstructions({python, skill, serial, token, url, server = 'tcp:localhost:5037', state, owned = true}) {
  return `Read ${skill}/SKILL.md for live device coordination.\n` +
    `Shared device: ${serial}. Take turns with the human; use your own actor label.\n` +
    `Private viewer URL (same screen as the desktop app): ${url}\n` +
    `Run commands on this ADB host. Keep the token and URL private.\n\n` +
    `export ADB_COORD_TOKEN=${shellQuote(token)}\n` +
    `export ADB_SERVER_SOCKET=${shellQuote(server)}\n` +
    (state ? `export ADB_COORD_STATE=${shellQuote(state)}\n` : '') +
    `export ADB_COORD_ACTOR='codex:your-thread-id' # or claude:/t3: with a unique thread ID\n` +
    `${shellQuote(python)} ${shellQuote(skill + '/scripts/adb_coord.py')} run --serial ${shellQuote(serial)} -- shell input tap 300 500\n` +
    `The last line is an example; inspect the screen before choosing coordinates.\n` +
    (owned ? 'Closing the desktop session releases its claim. ' : 'The desktop is borrowing the existing owner’s claim. ') +
    `Do not release or hand off a shared session while the human is using it.\n`;
}

module.exports = {viewerUrl, portNumber, shellQuote, agentInstructions};
