const {test} = require('node:test');
const assert = require('node:assert/strict');
const {execFileSync} = require('node:child_process');
const {viewerUrl, portNumber, shellQuote, agentInstructions, launchArguments, launchRequest} = require('../app/core.cjs');

test('development launcher flags and app entry are not project paths', () => {
  assert.deepEqual(launchArguments(['electron','--inspect=0','--remote-debugging-port=0','/source/desktop','.'],true), ['.']);
  assert.deepEqual(launchArguments(['electron','/source/desktop'],true), []);
  assert.deepEqual(launchArguments(['/opt/android-agent-lab','/work/app'],false), ['/work/app']);
});

test('project launch paths resolve against the calling terminal and remain literal', () => {
  assert.deepEqual(launchRequest([], '/work'), {mode:'launch'});
  assert.deepEqual(launchRequest(['.'], '/work/My app'), {mode:'project',path:'/work/My app'});
  assert.deepEqual(launchRequest(['--project','../Other app'], '/work/current'), {mode:'project',path:'/work/Other app'});
  assert.deepEqual(launchRequest(['--','-app'], '/work'), {mode:'project',path:'/work/-app'});
  assert.equal(launchRequest(["/work/$(touch bad) 'quoted'"], '/').path, "/work/$(touch bad) 'quoted'");
  assert.equal(launchRequest(['--remote-debugging-port=0','/work/app'], '/').path, '/work/app');
});

test('launch options are explicit and invalid commands do not open unintended directories', () => {
  for (const [arg,mode] of [['--help','help'],['-h','help'],['--version','version'],['-v','version'],['--smoke-test','smoke']]) assert.deepEqual(launchRequest([arg], '/work'), {mode});
  for (const args of [['--project'],['--project','--help'],['--unknown'],['a','b'],[''],['bad\0path'],['--version','.'],['.','--help']]) assert.throws(() => launchRequest(args, '/work'));
});

test('only private local viewer URLs may open in a desktop device window', () => {
  const key = 'a'.repeat(43);
  for (const host of ['127.0.0.1', 'localhost', '[::1]']) assert.equal(viewerUrl(`http://${host}:8766/#key=${key}`).port, '8766');
  for (const value of ['file:///etc/passwd', 'javascript:alert(1)', `https://evil.test/#key=${key}`,
    `http://localhost@evil.test/#key=${key}`, `http://user@localhost/#key=${key}`,
    'http://localhost:8766/', `http://localhost:8766/other#key=${key}`, `http://localhost/?key=${key}`]) {
    assert.throws(() => viewerUrl(value));
  }
});

test('ports reject privileged, fractional, and ambiguous values', () => {
  for (const value of [0, 1024, 8766, 65535]) assert.equal(portNumber(value), value);
  for (const value of [-1, 80, 65536, 1.5, '8766', NaN, undefined]) assert.throws(() => portNumber(value));
});

test('copied agent commands preserve arbitrary paths as literal shell arguments', () => {
  const value = "some path/'quote' $(printf wrong) `printf wrong`";
  assert.equal(execFileSync('bash', ['-c', `printf %s ${shellQuote(value)}`], {encoding: 'utf8'}), value);
  const text = agentInstructions({python:'python3',skill:'/tmp/a b/skill',serial:'127.0.0.1:15555',token:'private-token',url:'private-url'});
  assert.match(text, /run --serial '127\.0\.0\.1:15555' -- shell input/);
  assert.match(text, /ADB_COORD_ACTOR/);
  assert.match(text, /Closing the desktop session releases/);
});
