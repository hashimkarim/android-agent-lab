const {test} = require('node:test');
const assert = require('node:assert/strict');
const {execFileSync} = require('node:child_process');
const {viewerUrl, portNumber, shellQuote, agentInstructions} = require('../app/core.cjs');

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
