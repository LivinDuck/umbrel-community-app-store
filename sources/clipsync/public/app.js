const $ = id => document.getElementById(id);
const notice = message => { $('notice').textContent = message; };
async function api(path, method = 'GET', data) {
  const response = await fetch(path, { method, headers: data === undefined ? {} : { 'Content-Type': 'application/json' }, body: data === undefined ? undefined : JSON.stringify(data) });
  const value = await response.json();
  if (!response.ok) { if (response.status === 401) { $('settings').hidden = true; $('login').hidden = false; } throw new Error(value.error ?? 'Request failed'); }
  return value;
}
async function busy(button, work) { button.disabled = true; try { await work(); } catch (e) { notice(e.message); } finally { button.disabled = false; } }
async function refresh() {
  const state = await api('/admin/status');
  $('login').hidden = state.unlocked; $('settings').hidden = !state.unlocked; $('logout').hidden = !state.unlocked || state.authMode === 'umbrel';
  $('login-title').textContent = state.configured ? 'Unlock server settings' : 'Set a server settings password';
  $('login-help').textContent = state.configured ? 'Use the server password you chose during setup. Devices pair without accounts.' : 'Choose at least 12 characters to protect these settings. Your devices will use one-time codes, not this password.';
  if (!state.unlocked) return;
  const settings = await api('/admin/settings');
  $('url').value = settings.publicUrl;
  $('cf-token').placeholder = settings.hasCloudflareToken ? 'Token saved — leave blank to keep it' : 'Zone DNS Edit + Zone Read';
  $('tls-status').textContent = settings.tlsStatus;
  $('devices').replaceChildren();
  if (!settings.devices.length) { const li = document.createElement('li'); li.textContent = 'No devices paired yet.'; $('devices').append(li); }
  for (const device of settings.devices) {
    const li = document.createElement('li'), label = document.createElement('span'), status = document.createElement('small'), remove = document.createElement('button');
    label.textContent = device.name; status.textContent = device.connected ? 'Connected · receiving updates' : 'Offline · sync resumes on reconnect'; label.append(status);
    remove.textContent = 'Remove'; remove.setAttribute('aria-label', `Remove ${device.name}`);
    remove.onclick = () => { if (confirm(`Remove ${device.name}? It will need a new pairing code to reconnect.`)) busy(remove, async () => { await api(`/admin/devices/${encodeURIComponent(device.id)}`, 'DELETE'); await refresh(); }); };
    li.append(label, remove); $('devices').append(li);
  }
}
$('login-form').onsubmit = event => { event.preventDefault(); busy(event.submitter, async () => { await api('/admin/login', 'POST', { password: $('password').value }); $('password').value = ''; notice('Settings unlocked.'); await refresh(); }); };
$('network-form').onsubmit = event => { event.preventDefault(); busy(event.submitter, async () => { await api('/admin/settings', 'POST', { publicUrl: $('url').value.trim(), cloudflareToken: $('cf-token').value.trim(), clearCloudflareToken: $('clear-token').checked }); $('cf-token').value = ''; $('clear-token').checked = false; notice('Connection saved. Use the same full HTTPS address in both apps.'); await refresh(); }); };
$('pair').onclick = () => busy($('pair'), async () => { const result = await api('/admin/pairing', 'POST', {}); $('pair-result').hidden = false; $('pair-url').textContent = result.publicUrl; $('pair-code').textContent = result.code; $('pair-expiry').textContent = `One device only. Expires at ${new Date(result.expiresAt).toLocaleTimeString()}. Generate another code for your next device.`; });
$('refresh').onclick = () => busy($('refresh'), refresh);
$('logout').onclick = () => busy($('logout'), async () => { await api('/admin/logout', 'POST', {}); $('pair-result').hidden = true; notice('Settings locked.'); await refresh(); });
refresh().catch(e => notice(e.message));
