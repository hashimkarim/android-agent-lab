'use strict';
const path = require('node:path');

const launchHelp = `Usage: android-agent-lab [options] [project-directory]

Open Android Agent Lab, or add and select a Gradle project in its app library.
Existing projects keep their names, build tasks, application IDs and APK paths.

Examples:
  android-agent-lab .
  android-agent-lab "/home/you/My Android App"
  android-agent-lab --project ../my-app

Options:
  --project <directory>  Open a project root containing gradlew
  --help, -h            Show this help
  --version, -v         Show the app version
  --                    Treat the following argument as a literal path

Builds and device actions are available in Projects & APKs after opening.
`;

function launchArguments(argv, defaultApp) {
  const args = argv.slice(1);
  // In development Electron keeps its flags before the app entry in argv.
  // A packaged executable has no app entry to remove.
  return defaultApp ? args.slice(args.findIndex(arg => !arg.startsWith('-')) + 1) : args;
}

function launchRequest(args, cwd) {
  let project, mode = 'launch', literal = false;
  for (let i = 0; i < args.length; i++) {
    const arg = args[i];
    if (!literal && arg === '--') { literal = true; continue; }
    // These may be supplied by Electron launchers or the desktop test runner.
    if (!literal && /^(?:--(?:no-sandbox|disable-gpu|remote-debugging-pipe)|--(?:inspect(?:-brk)?|remote-debugging-port|ozone-platform|original-process-start-time)=.+)$/.test(arg)) continue;
    if (!literal && ['--help', '-h', '--version', '-v', '--smoke-test'].includes(arg)) {
      if (mode !== 'launch' || project !== undefined) throw new Error('Use help, version or smoke test on its own.');
      mode = ['--help', '-h'].includes(arg) ? 'help' : ['--version', '-v'].includes(arg) ? 'version' : 'smoke';
      continue;
    }
    if (mode !== 'launch') throw new Error('Use help, version or smoke test on its own.');
    if (project !== undefined) throw new Error('Open one project at a time. Quote paths containing spaces.');
    if (!literal && arg === '--project') {
      project = args[++i];
      if (!project || project.startsWith('-')) throw new Error('--project needs a directory. Use ./ before a name starting with a dash.');
    } else {
      if (!literal && arg.startsWith('-')) throw new Error(`Unknown option: ${arg}. Use --help for usage.`);
      project = arg;
    }
    if (!project || project.includes('\0')) throw new Error('Enter a project directory.');
  }
  return project === undefined ? {mode} : {mode: 'project', path: path.resolve(cwd, project)};
}

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

module.exports = {viewerUrl, portNumber, shellQuote, agentInstructions, launchArguments, launchRequest, launchHelp};
