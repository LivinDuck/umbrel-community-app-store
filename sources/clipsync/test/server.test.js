import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { once } from 'node:events';
import { WebSocket } from 'ws';
import { createClipSync, caddyConfig, validateItem } from '../src/server.js';

const password = 'disposable-test-password';
const deviceId = 'test-device-1234';
const item = { id: 'clip-1', text: 'hello from Mac', timestamp: Date.now(), deviceId, deviceName: 'Mac', contentType: 'text' };

async function fixture() {
  const dataDir = mkdtempSync(join(tmpdir(), 'clipsync-'));
  let app, api, web;
  async function start() {
    app = await createClipSync({ dataDir, host: '127.0.0.1', apiPort: 0, webPort: 0, adminPassword: password });
    const ports = await app.listen(); api = `http://127.0.0.1:${ports.apiPort}`; web = `http://127.0.0.1:${ports.webPort}`;
  }
  await start();
  let cookie;
  async function request(path, { method = 'GET', data, token, admin = false, expected = 200, headers = {} } = {}) {
    const response = await fetch((admin ? web : api) + path, { method, headers: { ...(data === undefined ? {} : { 'Content-Type': 'application/json' }),
      ...(token ? { Authorization: `Bearer ${token}` } : {}), ...(admin && cookie ? { Cookie: cookie } : {}), ...headers }, body: data === undefined ? undefined : JSON.stringify(data) });
    assert.equal(response.status, expected, `${path}: ${response.status}`);
    const setCookie = response.headers.get('set-cookie'); if (setCookie) cookie = setCookie.split(';')[0];
    return response.json();
  }
  async function unlock() { await request('/admin/login', { admin: true, method: 'POST', data: { password } }); }
  async function pair(id = deviceId) {
    const { code } = await request('/admin/pairing', { admin: true, method: 'POST', data: {} });
    return request('/v1/pair', { method: 'POST', data: { code, deviceId: id, deviceName: 'Test device' } });
  }
  const connect = token => new WebSocket(api.replace('http:', 'ws:') + '/v1/events', { headers: { Authorization: `Bearer ${token}` } });
  return { request, unlock, pair, connect, async restart() { await app.close(); await start(); },
    async close() { await app.close(); rmSync(dataDir, { recursive: true, force: true }); } };
}

test('pair, instant push, image, reconnect snapshot, persistent credentials, and revocation', async () => {
  const f = await fixture();
  try {
    await f.request('/admin/settings', { admin: true, expected: 401 });
    await f.request('/admin/settings', { expected: 404 }); // Never expose settings on the WAN port.
    await f.request('/v1/clipboard', { expected: 401 });
    await f.unlock();
    await f.request('/admin/settings', { admin: true, method: 'POST', data: { publicUrl: 'https://sync.example.com:39443' } });
    const { code } = await f.request('/admin/pairing', { admin: true, method: 'POST', data: {} });
    const paired = await f.request('/v1/pair', { method: 'POST', data: { code, deviceId, deviceName: 'Mac' } });
    await f.request('/v1/pair', { method: 'POST', data: { code, deviceId: 'another-device', deviceName: 'Phone' }, expected: 403 });
    const receiver = await f.pair('phone-device-1234');
    let ws = f.connect(receiver.token);
    const [first] = await once(ws, 'message'); assert.equal(JSON.parse(first).item, null);
    const delivered = once(ws, 'message');
    await f.request('/v1/clipboard', { method: 'PUT', token: paired.token, data: item });
    assert.deepEqual(JSON.parse((await delivered)[0]).item, item);
    const image = { ...item, id: 'image-1', text: '', contentType: 'image', imageData: Buffer.alloc(1_500_000, 7).toString('base64'), mimeType: 'image/png', imageName: 'Clipboard image' };
    const deliveredImage = once(ws, 'message');
    await f.request('/v1/clipboard', { method: 'PUT', token: paired.token, data: image });
    assert.deepEqual(JSON.parse((await deliveredImage)[0]).item, image);
    ws.terminate(); await once(ws, 'close');
    await f.restart();
    assert.deepEqual(await f.request('/v1/clipboard', { token: paired.token }), image);
    ws = f.connect(receiver.token);
    assert.deepEqual(JSON.parse((await once(ws, 'message'))[0]).item, image);
    await f.unlock();
    const closed = once(ws, 'close');
    await f.request('/admin/devices/phone-device-1234', { admin: true, method: 'DELETE' });
    assert.equal((await closed)[0], 4001);
    await f.request('/v1/clipboard', { token: receiver.token, expected: 401 });
  } finally { await f.close(); }
});

test('reject unauthenticated, oversized, spoofed, and cross-origin requests', async () => {
  const f = await fixture();
  try {
    await f.request('/admin/login', { admin: true, method: 'POST', data: { password }, headers: { Origin: 'https://evil.example' }, expected: 403 });
    await f.unlock();
    await f.request('/admin/settings', { admin: true, method: 'POST', data: { publicUrl: 'http://example.com' }, expected: 400 });
    await f.request('/admin/settings', { admin: true, method: 'POST', data: { publicUrl: 'https://sync.example.com:39443' } });
    const { token } = await f.pair();
    await f.request('/v1/clipboard', { method: 'PUT', token, data: { ...item, deviceId: 'someone-else' }, expected: 403 });
    await f.request('/v1/clipboard', { method: 'PUT', token, data: { ...item, text: 'x'.repeat(32769) }, expected: 400 });
    await f.request('/v1/clipboard', { method: 'PUT', token, data: { ...item, imageData: '!', contentType: 'image' }, expected: 400 });
    assert.equal((await f.request('/admin/settings', { admin: true })).hasCloudflareToken, false);
    for (let i=0; i<20; i++) await f.request('/v1/pair', { method: 'POST', data: { code: 'invalid' }, expected: i<19 ? 403 : 429 });
  } finally { await f.close(); }
});

test('TLS config uses DNS validation and only the dedicated port; strips local image URI', () => {
  const config = caddyConfig({ publicUrl: 'https://sync.example.com:39443', cloudflareToken: 'test-only-placeholder' });
  assert.deepEqual(config.apps.http.servers.clipsync.listen, [':8443']);
  assert.equal(config.apps.http.servers.clipsync.automatic_https.disable_redirects, true);
  const challenges = config.apps.tls.automation.policies[0].issuers[0].challenges;
  assert.equal(challenges.http.disabled, true); assert.equal(challenges['tls-alpn'].disabled, true);
  assert.equal(challenges.dns.provider.name, 'cloudflare');
  assert.equal(validateItem({ ...item, localImageUri: 'content://private' }, { id: deviceId, name: 'Mac' }).localImageUri, undefined);
});
