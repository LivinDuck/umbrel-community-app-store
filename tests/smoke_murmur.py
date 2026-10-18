#!/usr/bin/env python3
"""Run the packaged Murmur image against a disposable Hermes protocol fixture."""
import json
import os
from pathlib import Path
import secrets
import subprocess
import tempfile
import time
import urllib.error
import urllib.request

import yaml

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / 'livinduck-murmur-web'

# Test both dashboard token and password sign-in; no agents or model calls.
FIXTURE = r"""
const http = require('node:http');
const token = 'fixture-session-' + require('node:crypto').randomBytes(16).toString('hex');
const gated = process.env.FIXTURE_AUTH === 'password';
http.createServer(async (req, res) => {
  const path = new URL(req.url, 'http://fixture').pathname;
  if (path === '/') {
    res.setHeader('Content-Type', 'text/html');
    return res.end(gated ? '<script>window.__HERMES_AUTH_REQUIRED__ = true;</script>' : '<script>window.__HERMES_SESSION_TOKEN__ = "' + token + '";</script>');
  }
  res.setHeader('Content-Type', 'application/json');
  if (path === '/api/status') return res.end(JSON.stringify({
    version: '2026.9.24', auth_required: gated, install_id: 'murmur-ci-fixture'
  }));
  if (path === '/api/auth/providers') return res.end('{"providers":[{"name":"basic","supports_password":true}]}');
  if (path === '/auth/password-login') {
    let raw = ''; for await (const chunk of req) raw += chunk;
    const body = JSON.parse(raw);
    if (body.username !== 'fixture-user' || body.password !== 'fixture-password') {
      res.statusCode = 401; return res.end('{}');
    }
    res.setHeader('Set-Cookie', 'hermes_session_at=' + token + '; Path=/; Max-Age=900; HttpOnly');
    return res.end('{}');
  }
  if (gated ? req.headers.authorization !== 'Bearer ' + token : req.headers['x-hermes-session-token'] !== token) {
    res.statusCode = 401;
    return res.end('{"error":"unauthorized"}');
  }
  if (path === '/api/sessions') return res.end('{"sessions":[{"id":"existing-chat","title":"Existing Hermes conversation"}]}');
  res.end('{}');
}).listen(18789, '0.0.0.0');
"""


def main(auth):
    package = yaml.safe_load((APP / 'docker-compose.yml').read_text())
    manifest = yaml.safe_load((APP / 'umbrel-app.yml').read_text())
    assert set(package['services']) == {'app_proxy', 'web'}
    assert manifest['dependencies'] == ['hermes-agent']
    proxy = package['services'].pop('app_proxy')['environment']
    assert proxy['APP_HOST'] == manifest['id'] + '_web_1'
    assert proxy.get('PROXY_AUTH_ADD') != 'false'
    assert all(path.endswith(('.png', '.svg', '.webmanifest'))
               for path in proxy['PROXY_AUTH_WHITELIST'].split(','))
    web = package['services']['web']
    assert 'ports' not in web and 'network_mode' not in web
    assert not any(key.startswith('MURMUR_BUILTIN_HERMES_') for key in web['environment'])
    assert 'HERMES_URL' not in web['environment']
    hermes_url = 'http://hermes-agent_web_1:18789'
    package.pop('version', None)

    with tempfile.TemporaryDirectory(prefix='murmur-smoke-') as tmp:
        work = Path(tmp)
        data = work / 'data/murmur'
        data.mkdir(parents=True)
        # Emulate Umbrel's uid 1000 app data ownership, not world-writable state.
        subprocess.run(['sudo', 'chown', '-R', '1000:1000', str(data)], check=True)
        fixture = work / 'fixture.cjs'
        fixture.write_text(FIXTURE)
        web['ports'] = ['127.0.0.1::3000']
        package['services']['hermes-fixture'] = {
            'image': web['image'],
            'init': True,
            'command': ['node', '/fixture.cjs'],
            'environment': {'FIXTURE_AUTH': auth},
            'volumes': [str(fixture) + ':/fixture.cjs:ro'],
            'networks': {'default': {'aliases': ['hermes-agent_web_1']}},
            'healthcheck': {
                'test': ['CMD', 'wget', '-qO-', 'http://127.0.0.1:18789/api/status'],
                'interval': '2s', 'timeout': '2s', 'retries': 10,
            },
        }
        file = work / 'compose.yml'
        file.write_text(yaml.safe_dump(package, sort_keys=False))
        env = dict(os.environ, APP_DATA_DIR=tmp)
        project = 'murmur-smoke-' + secrets.token_hex(4)

        def compose(*args, capture=False):
            return subprocess.run(
                ['docker', 'compose', '-p', project, '-f', str(file), *args],
                env=env, check=True, text=True, capture_output=capture)

        base = ''

        def request(path, body=None, method=None, origin=None):
            headers = {'Content-Type': 'application/json', 'Origin': origin or base}
            req = urllib.request.Request(
                base + path, headers=headers, method=method,
                data=json.dumps(body).encode() if body is not None else None)
            try:
                with urllib.request.urlopen(req, timeout=20) as response:
                    return response.status, response.read().decode()
            except urllib.error.HTTPError as error:
                return error.code, error.read().decode()

        def ready():
            nonlocal base
            port = compose('port', 'web', '3000', capture=True).stdout.strip().rsplit(':', 1)[1]
            base = 'http://127.0.0.1:' + port
            for attempt in range(30):
                try:
                    code, body = request('/murmur/connection')
                    if code == 200 and json.loads(body)['status'] == 'connected':
                        return json.loads(body)
                except (OSError, ValueError):
                    pass
                time.sleep(2)
            raise AssertionError('Murmur could not connect to the external Hermes fixture')

        def saved_settings():
            return json.loads(compose('exec', '-T', 'web', 'node', '-e',
                "process.stdout.write(require('node:fs').readFileSync('/data/murmur.json'))",
                capture=True).stdout)

        try:
            # Password case also exercises an update from the original fixed URL.
            if auth == 'password':
                web['environment']['HERMES_URL'] = hermes_url
                file.write_text(yaml.safe_dump(package, sort_keys=False))
                compose('up', '-d', '--wait', '--wait-timeout', '120')
                assert saved_settings()['setupSeen']
                del web['environment']['HERMES_URL']
                file.write_text(yaml.safe_dump(package, sort_keys=False))
            compose('up', '-d', '--wait', '--wait-timeout', '120')
            port = compose('port', 'web', '3000', capture=True).stdout.strip().rsplit(':', 1)[1]
            base = 'http://127.0.0.1:' + port
            code, body = request('/murmur/setup')
            setup = json.loads(body)
            assert code == 200 and not setup['decided'] and setup['builtin'] is None, setup
            found = next(item for item in setup['found'] if item['url'] == hermes_url)
            credentials = {'username': 'fixture-user', 'password': 'fixture-password'} if auth == 'password' else {}
            if auth == 'password':
                assert found['needsSignIn']
                assert request('/murmur/setup', {'use': 'found', 'id': found['id']})[0] == 422
                assert request('/murmur/setup', {'use': 'found', 'id': found['id'], 'username': 'fixture-user', 'password': 'wrong'})[0] == 422
                assert not json.loads(request('/murmur/setup')[1])['decided']
            code, body = request('/murmur/setup', {'use': 'found', 'id': found['id'], **credentials})
            assert code == 200, body
            connected = ready()
            assert connected['source'] == 'saved' and not connected['managed']
            connection_path = '/murmur/connections/' + connected['id']
            assert connected['url'] == hermes_url
            assert 'fixture-session-' not in json.dumps(connected)
            code, html = request('/')
            assert code == 200 and '<html' in html and '/assets/' in html
            code, body = request('/murmur/setup')
            setup = json.loads(body)
            assert code == 200 and setup['decided'] and setup['builtin'] is None
            code, body = request('/hermes/api/sessions')
            assert code == 200 and 'existing-chat' in body
            assert 'fixture-session-' not in body
            assert request('/hermes/api/sessions', origin='https://untrusted.example')[0] == 403
            assert request(connection_path, {'name': 'Untrusted'}, 'PATCH',
                           origin='https://untrusted.example')[0] == 403
            assert request(connection_path, {'url': hermes_url, **credentials}, 'PATCH')[0] == 200
            assert request(connection_path, {'name': 'My existing Hermes'}, 'PATCH')[0] == 200
            settings = saved_settings()
            assert settings['connections'][0]['name'] == 'My existing Hermes'
            mode = compose('exec', '-T', 'web', 'node', '-e',
                "console.log(require('node:fs').statSync('/data/murmur.json').mode & 0o777)",
                capture=True).stdout.strip()
            assert int(mode) == 0o600

            compose('restart', 'web')
            assert ready()['name'] == 'My existing Hermes'
            compose('up', '-d', '--force-recreate', '--wait', '--wait-timeout', '120', 'web')
            assert ready()['name'] == 'My existing Hermes'
            assert saved_settings() == settings

            # Hermes restarts rotate its token. Murmur must recover without storing it.
            compose('restart', 'hermes-fixture')
            for attempt in range(30):
                code, body = request('/hermes/api/sessions')
                if code == 200 and 'existing-chat' in body:
                    break
                time.sleep(2)
            else:
                raise AssertionError('Hermes token refresh failed after restart')
            assert request(connection_path, method='DELETE')[0] == 200
            assert not json.loads(request('/murmur/setup')[1])['decided']
            print(f'PASS ({auth}): server choice, sign-in, editable connection, persistence and reconnect')
        except Exception:
            compose('logs', '--tail', '80')
            raise
        finally:
            compose('down', '--volumes', '--remove-orphans')
            subprocess.run(['sudo', 'rm', '-rf', str(work / 'data')], check=True)


if __name__ == '__main__':
    for auth in ('token', 'password'):
        main(auth)
