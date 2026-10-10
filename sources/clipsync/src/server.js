import http from 'node:http';
import { DatabaseSync } from 'node:sqlite';
import { randomBytes, randomInt, createHash, timingSafeEqual, scryptSync } from 'node:crypto';
import { mkdirSync, readFileSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { WebSocketServer, WebSocket } from 'ws';

const root = dirname(fileURLToPath(import.meta.url));
const hash = value => createHash('sha256').update(value).digest('hex');
const secret = () => randomBytes(32).toString('base64url');
const equal = (a, b) => timingSafeEqual(Buffer.from(hash(a)), Buffer.from(hash(b)));
const fail = (status, message) => Object.assign(new Error(message), { status });
const MAX_BODY = 2_100_000;

export function validateItem(item, device) {
  if (!item || typeof item !== 'object' || Array.isArray(item)) throw fail(400, 'Invalid clipboard');
  for (const key of ['id', 'deviceId', 'deviceName']) {
    if (typeof item[key] !== 'string' || !item[key].length || item[key].length > 200) throw fail(400, `Invalid ${key}`);
  }
  if (item.deviceId !== device.id) throw fail(403, 'Device identity does not match pairing');
  if (!Number.isSafeInteger(item.timestamp) || item.timestamp < 0) throw fail(400, 'Invalid timestamp');
  if (typeof item.text !== 'string' || item.text.length > 32768) throw fail(400, 'Text exceeds 32,768 characters');
  const result = { id: item.id, text: item.text, timestamp: item.timestamp, deviceId: device.id,
    deviceName: device.name, contentType: item.contentType ?? 'text' };
  if (result.contentType === 'image') {
    if (typeof item.imageData !== 'string' || item.imageData.length > 2_000_000 || !/^[A-Za-z0-9+/]*={0,2}$/.test(item.imageData)) throw fail(400, 'Invalid image');
    const bytes = Buffer.from(item.imageData, 'base64');
    if (bytes.toString('base64') !== item.imageData) throw fail(400, 'Invalid image encoding');
    if (!bytes.length || bytes.length > 1_500_000) throw fail(413, 'Image exceeds 1.5 MB');
    if (!['image/png', 'image/jpeg', 'image/webp', 'image/gif'].includes(item.mimeType)) throw fail(400, 'Unsupported image type');
    result.imageData = item.imageData; result.mimeType = item.mimeType;
    result.imageName = typeof item.imageName === 'string' ? item.imageName.slice(0, 200) : 'Clipboard image';
  } else if (result.contentType !== 'text' || !item.text.length) throw fail(400, 'Invalid text clipboard');
  return result;
}

export function caddyConfig(settings, upstream = 'server:3001') {
  if (!settings.publicUrl || !settings.cloudflareToken) return { admin: { listen: '0.0.0.0:2019' } };
  const hostname = new URL(settings.publicUrl).hostname;
  return {
    admin: { listen: '0.0.0.0:2019' },
    apps: {
      http: { servers: { clipsync: {
        listen: [':8443'], protocols: ['h1', 'h2'],
        automatic_https: { disable_redirects: true },
        routes: [{ match: [{ host: [hostname] }], handle: [{ handler: 'reverse_proxy', upstreams: [{ dial: upstream }] }], terminal: true }]
      } } },
      tls: { automation: { policies: [{ subjects: [hostname], issuers: [{ module: 'acme',
        challenges: { http: { disabled: true }, 'tls-alpn': { disabled: true },
          dns: { provider: { name: 'cloudflare', api_token: settings.cloudflareToken } } }
      }] }] } }
    }
  };
}

export async function createClipSync(options = {}) {
  const adminAuth = options.adminAuth ?? process.env.ADMIN_AUTH ?? 'password';
  if (!['password', 'umbrel'].includes(adminAuth)) throw new Error('ADMIN_AUTH must be password or umbrel');
  const dataDir = options.dataDir ?? process.env.DATA_DIR ?? './data';
  mkdirSync(dataDir, { recursive: true, mode: 0o700 });
  const db = new DatabaseSync(join(dataDir, 'clipsync.sqlite'));
  db.exec(`PRAGMA journal_mode=WAL; PRAGMA synchronous=FULL;
    CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS devices (id TEXT PRIMARY KEY, name TEXT NOT NULL, token_hash TEXT NOT NULL UNIQUE, created INTEGER NOT NULL);
    CREATE TABLE IF NOT EXISTS clipboard (singleton INTEGER PRIMARY KEY CHECK(singleton=1), json TEXT NOT NULL);
    PRAGMA user_version=1;`);
  const get = key => { const row = db.prepare('SELECT value FROM settings WHERE key=?').get(key); return row ? JSON.parse(row.value) : null; };
  const set = (key, value) => db.prepare('INSERT OR REPLACE INTO settings VALUES (?,?)').run(key, JSON.stringify(value));
  const adminPassword = options.adminPassword ?? process.env.ADMIN_PASSWORD;
  const sessions = new Map(), codes = new Map(), limits = new Map();
  const sockets = new WebSocketServer({ noServer: true, maxPayload: 1024, perMessageDeflate: false });
  let tlsStatus = 'Not configured', closing = false;
  const caddyAdmin = options.caddyAdmin ?? process.env.CADDY_ADMIN_URL;
  const upstream = options.upstream ?? process.env.SYNC_UPSTREAM ?? 'server:3001';
  const now = () => Date.now();
  const current = () => { const row = db.prepare('SELECT json FROM clipboard WHERE singleton=1').get(); return row ? JSON.parse(row.json) : null; };
  const configured = () => Boolean(adminPassword || get('password'));
  const networkSettings = () => get('network') ?? {};
  function json(res, status, data) {
    res.writeHead(status, { 'Content-Type': 'application/json', 'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff' });
    res.end(JSON.stringify(data));
  }
  function limited(req, kind, max) {
    // Ignore forwarded headers: an Internet client must not choose its rate-limit identity.
    const key = `${kind}:${req.socket.remoteAddress}`;
    let entry = limits.get(key);
    if (!entry || entry.until < now()) { entry = { count: 0, until: now() + 60_000 }; limits.set(key, entry); }
    if (++entry.count > max) throw fail(429, 'Too many attempts. Try again in a minute.');
  }
  async function body(req, limit = MAX_BODY) {
    if (!req.headers['content-type']?.startsWith('application/json')) throw fail(415, 'Send application/json');
    let size = 0; const chunks = [];
    for await (const chunk of req) {
      size += chunk.length;
      if (size > limit) throw fail(413, 'Request too large');
      chunks.push(chunk);
    }
    try { return JSON.parse(Buffer.concat(chunks).toString()); } catch { throw fail(400, 'Invalid JSON'); }
  }
  function device(req) {
    const token = req.headers.authorization?.match(/^Bearer ([A-Za-z0-9_-]{43})$/)?.[1];
    const result = token && db.prepare('SELECT id,name FROM devices WHERE token_hash=?').get(hash(token));
    if (!result) throw fail(401, 'Device is not paired. Pair again in ClipSync settings.');
    return result;
  }
  function admin(req) {
    // Explicit deployment setting: the private dashboard is behind Umbrel app_proxy.
    // This never changes authentication on the separate native/WAN listener.
    if (adminAuth === 'umbrel') return;
    const token = req.headers.cookie?.match(/(?:^|;\s*)clipsync_session=([A-Za-z0-9_-]+)/)?.[1];
    if (!token || (sessions.get(hash(token)) ?? 0) < now()) throw fail(401, 'Unlock the server settings first');
  }
  function checkOrigin(req) {
    const origin = req.headers.origin;
    if (origin && new URL(origin).host !== req.headers.host && new URL(origin).host !== req.headers['x-forwarded-host']) throw fail(403, 'Invalid origin');
    if (req.headers['sec-fetch-site'] === 'cross-site') throw fail(403, 'Invalid origin');
  }
  // Node fetch adds browser Fetch Metadata headers; Caddy correctly applies its
  // browser-origin checks to those. This is a private service-to-service request.
  function requestCaddy(path, method = 'GET', config) {
    return new Promise((resolve, reject) => {
      const request = http.request(new URL(caddyAdmin + path), {
        method, headers: config ? { 'Content-Type': 'application/json' } : {}
      }, response => {
        response.resume();
        resolve({ ok: response.statusCode >= 200 && response.statusCode < 300 });
      });
      request.setTimeout(5000, () => request.destroy(new Error('HTTPS helper timed out')));
      request.on('error', reject);
      request.end(config ? JSON.stringify(config) : undefined);
    });
  }
  async function configureTLS() {
    if (!caddyAdmin) { tlsStatus = 'Use an existing HTTPS reverse proxy, or deploy the bundled HTTPS helper'; return; }
    try {
      const response = await requestCaddy('/load', 'POST', caddyConfig(networkSettings(), upstream));
      if (!response.ok) throw new Error('TLS configuration rejected');
      tlsStatus = networkSettings().cloudflareToken ? 'Automatic HTTPS configured. Certificate issuance/renewal runs in the background; test the public URL before pairing.' : 'Built-in HTTPS disabled. Use an existing HTTPS reverse proxy, or configure Cloudflare above.';
    } catch { tlsStatus = 'HTTPS proxy is unavailable or rejected configuration. Retrying automatically.'; }
  }
  const api = http.createServer(async (req, res) => {
    try {
      const path = new URL(req.url, 'http://local').pathname;
      if (req.method === 'GET' && path === '/health') return json(res, 200, { service: 'clipsync', version: 1 });
      if (req.method === 'POST' && path === '/v1/pair') {
        limited(req, 'pair', 20);
        const input = await body(req, 4096);
        const code = String(input.code ?? '').toUpperCase().replace(/[\s-]/g, '');
        const entry = codes.get(hash(code));
        if (!entry || entry.expiresAt < now()) throw fail(403, 'Pairing code is invalid or expired. Generate a new code in Umbrel.');
        if (typeof input.deviceId !== 'string' || !/^[A-Za-z0-9_-]{8,100}$/.test(input.deviceId) || typeof input.deviceName !== 'string' || !input.deviceName.trim() || input.deviceName.length > 200) throw fail(400, 'Invalid device details');
        if (db.prepare('SELECT count(*) AS n FROM devices').get().n >= 100) throw fail(409, 'Device limit reached. Remove an old device.');
        // Consume only after the transaction succeeds. A repeated device ID rotates its token.
        const token = secret();
        db.prepare('INSERT OR REPLACE INTO devices VALUES (?,?,?,?)').run(input.deviceId, input.deviceName.trim(), hash(token), now());
        codes.delete(hash(code));
        for (const ws of sockets.clients) if (ws.device.id === input.deviceId) ws.close(4001, 'Pairing replaced');
        return json(res, 200, { token, deviceId: input.deviceId });
      }
      if (path !== '/v1/clipboard') throw fail(404, 'Not found');
      const paired = device(req);
      if (req.method === 'GET') return json(res, 200, current());
      if (req.method === 'PUT') {
        limited(req, 'write', 240);
        const item = validateItem(await body(req), paired);
        const encoded = JSON.stringify(item);
        // Persist before acknowledging or broadcasting; reconnect always gets this snapshot.
        db.prepare('INSERT OR REPLACE INTO clipboard VALUES (1,?)').run(encoded);
        const message = JSON.stringify({ type: 'clipboard', item });
        for (const ws of sockets.clients) {
          if (ws.readyState !== WebSocket.OPEN) continue;
          if (ws.bufferedAmount > MAX_BODY * 2) { ws.terminate(); continue; }
          ws.send(message);
        }
        return json(res, 200, { ok: true });
      }
      throw fail(405, 'Method not allowed');
    } catch (error) { if (!res.headersSent) json(res, error.status ?? 500, { error: error.status ? error.message : 'Server error' }); }
  });
  api.on('upgrade', (req, socket, head) => {
    try {
      if (new URL(req.url, 'http://local').pathname !== '/v1/events' || req.headers.origin) throw fail(403, 'Invalid WebSocket request');
      const paired = device(req);
      if ([...sockets.clients].filter(ws => ws.device.id === paired.id).length >= 4) throw fail(429, 'Too many connections');
      sockets.handleUpgrade(req, socket, head, ws => {
        ws.device = paired; ws.alive = true;
        ws.on('error', () => {});
        ws.on('pong', () => { ws.alive = true; });
        ws.on('message', () => ws.close(1008, 'Use HTTPS PUT to publish'));
        ws.send(JSON.stringify({ type: 'clipboard', item: current() }));
      });
    } catch (error) { socket.end(`HTTP/1.1 ${error.status ?? 400} Rejected\r\nConnection: close\r\n\r\n`); }
  });
  const web = http.createServer(async (req, res) => {
    try {
      const path = new URL(req.url, 'http://local').pathname;
      checkOrigin(req);
      if (req.method === 'GET' && path === '/favicon.ico') { res.writeHead(204); return res.end(); }
      if (req.method === 'GET' && ['/','/app.js','/style.css'].includes(path)) {
        const file = path === '/' ? 'index.html' : path.slice(1);
        res.writeHead(200, { 'Content-Type': file.endsWith('.html') ? 'text/html; charset=utf-8' : file.endsWith('.js') ? 'text/javascript' : 'text/css',
          'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff', 'Referrer-Policy': 'no-referrer',
          'Content-Security-Policy': "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; frame-ancestors 'self'; base-uri 'none'; form-action 'self'" });
        return res.end(readFileSync(join(root, '../public', file)));
      }
      if (req.method === 'GET' && path === '/admin/status') {
        let unlocked = false; try { admin(req); unlocked = true; } catch {}
        return json(res, 200, { configured: configured(), unlocked, authMode: adminAuth });
      }
      if (adminAuth === 'umbrel' && ['/admin/login', '/admin/logout'].includes(path)) throw fail(404, 'Use Umbrel to manage your session');
      if (req.method === 'POST' && path === '/admin/login') {
        limited(req, 'login', 8);
        const input = await body(req, 4096);
        if (typeof input.password !== 'string' || input.password.length < 12 || input.password.length > 256) throw fail(400, 'Use a password of 12–256 characters');
        if (!configured()) {
          const salt = secret(); set('password', { salt, value: scryptSync(input.password, salt, 32).toString('hex') });
        }
        const saved = get('password');
        const valid = adminPassword ? equal(input.password, adminPassword) : equal(scryptSync(input.password, saved.salt, 32).toString('hex'), saved.value);
        if (!valid) throw fail(401, 'Incorrect server password');
        const token = secret(); sessions.set(hash(token), now() + 8 * 60 * 60_000);
        const secure = req.headers['x-forwarded-proto'] === 'https' ? '; Secure' : '';
        res.setHeader('Set-Cookie', `clipsync_session=${token}; HttpOnly; SameSite=Strict; Path=/; Max-Age=28800${secure}`);
        return json(res, 200, { ok: true });
      }
      admin(req);
      if (req.method === 'POST' && path === '/admin/logout') {
        const token = req.headers.cookie?.match(/clipsync_session=([^;]+)/)?.[1]; if (token) sessions.delete(hash(token));
        res.setHeader('Set-Cookie', 'clipsync_session=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0');
        return json(res, 200, { ok: true });
      }
      if (req.method === 'GET' && path === '/admin/settings') {
        const settings = networkSettings();
        return json(res, 200, { publicUrl: settings.publicUrl ?? '', hasCloudflareToken: Boolean(settings.cloudflareToken), tlsStatus,
          devices: db.prepare('SELECT id,name,created FROM devices ORDER BY created').all().map(d => ({ ...d, connected: [...sockets.clients].some(ws => ws.device.id === d.id && ws.readyState === WebSocket.OPEN) })) });
      }
      if (req.method === 'POST' && path === '/admin/settings') {
        const input = await body(req, 8192); let url;
        try { url = new URL(input.publicUrl); } catch { throw fail(400, 'Enter an HTTPS server URL'); }
        if (url.protocol !== 'https:' || url.username || url.password || url.search || url.hash || url.pathname !== '/') throw fail(400, 'Use https://your-hostname:port with no path');
        const settings = { publicUrl: url.origin, cloudflareToken: networkSettings().cloudflareToken ?? '' };
        if (input.cloudflareToken) {
          if (typeof input.cloudflareToken !== 'string' || !/^[A-Za-z0-9_-]{20,200}$/.test(input.cloudflareToken)) throw fail(400, 'Invalid Cloudflare API token format');
          settings.cloudflareToken = input.cloudflareToken;
        }
        if (input.clearCloudflareToken === true) settings.cloudflareToken = '';
        if (settings.cloudflareToken && (!url.hostname.includes('.') || /^[\d.]+$/.test(url.hostname) || url.hostname.includes(':'))) throw fail(400, 'DNS validation needs a public hostname');
        set('network', settings); await configureTLS();
        return json(res, 200, { ok: true, tlsStatus });
      }
      if (req.method === 'POST' && path === '/admin/pairing') {
        await body(req, 4096);
        if (!networkSettings().publicUrl) throw fail(409, 'Save the public HTTPS address first');
        if (codes.size >= 20) codes.clear();
        const alphabet = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789';
        const code = Array.from({ length: 10 }, () => alphabet[randomInt(alphabet.length)]).join('');
        const expiresAt = now() + 5 * 60_000; codes.set(hash(code), { expiresAt });
        return json(res, 200, { code: `${code.slice(0,5)}-${code.slice(5)}`, expiresAt, publicUrl: networkSettings().publicUrl });
      }
      if (req.method === 'DELETE' && path.startsWith('/admin/devices/')) {
        const id = decodeURIComponent(path.slice('/admin/devices/'.length));
        db.prepare('DELETE FROM devices WHERE id=?').run(id);
        for (const ws of sockets.clients) if (ws.device.id === id) ws.close(4001, 'Pairing revoked');
        return json(res, 200, { ok: true });
      }
      throw fail(404, 'Not found');
    } catch (error) { if (!res.headersSent) json(res, error.status ?? 500, { error: error.status ? error.message : 'Server error' }); }
  });
  for (const server of [api, web]) { server.requestTimeout = 30_000; server.headersTimeout = 15_000; server.maxHeadersCount = 40; }
  const heartbeat = setInterval(() => {
    for (const ws of sockets.clients) { if (!ws.alive) { ws.terminate(); continue; } ws.alive = false; ws.ping(); }
    for (const map of [sessions, codes, limits]) for (const [key, value] of map) if ((typeof value === 'number' ? value : value.expiresAt ?? value.until) < now()) map.delete(key);
  }, 25_000);
  heartbeat.unref();
  let appliedTLS = '';
  const tlsRetry = setInterval(async () => {
    if (closing || !caddyAdmin || !networkSettings().cloudflareToken) return;
    // Reapply after a proxy restart; never require a user-run restart.
    try {
      const res = await requestCaddy('/config/apps/http/servers/clipsync');
      if (!res.ok || tlsStatus.startsWith('HTTPS proxy') || appliedTLS !== JSON.stringify(networkSettings())) {
        await configureTLS(); appliedTLS = JSON.stringify(networkSettings());
      }
    } catch { await configureTLS(); }
  }, 15_000);
  tlsRetry.unref();
  return {
    api, web,
    async listen() {
      const host = options.host ?? process.env.HOST ?? '0.0.0.0';
      const start = (server, port) => new Promise((resolve, reject) => { server.once('error', reject); server.listen(port, host, resolve); });
      await start(api, options.apiPort ?? Number(process.env.API_PORT ?? 3001));
      await start(web, options.webPort ?? Number(process.env.PORT ?? 3000));
      await configureTLS();
      return { apiPort: api.address().port, webPort: web.address().port };
    },
    async close() {
      closing = true; clearInterval(heartbeat); clearInterval(tlsRetry);
      for (const ws of sockets.clients) ws.terminate();
      await new Promise(resolve => sockets.close(resolve));
      await Promise.all([api, web].map(server => new Promise(resolve => { server.close(resolve); server.closeAllConnections(); })));
      db.close();
    }
  };
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  process.umask(0o077);
  const app = await createClipSync();
  await app.listen();
  console.log('ClipSync is ready. Open the browser setup page to configure networking and pair devices.');
  const stop = async () => { await app.close(); process.exit(0); };
  process.on('SIGTERM', stop); process.on('SIGINT', stop);
}
