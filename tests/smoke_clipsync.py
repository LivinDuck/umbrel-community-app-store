"""Disposable Docker integration checks. Never connects to the user's NAS or DNS."""
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import tempfile
import time
import urllib.request
import urllib.error
import uuid
import yaml
import websocket

ROOT = Path(__file__).resolve().parents[1]
compose = yaml.safe_load((ROOT / 'livinduck-clipsync/docker-compose.yml').read_text())
server_image = compose['services']['server']['image']
tls_image = compose['services']['tls']['image']
name = 'clipsync-test-' + uuid.uuid4().hex[:10]
password = secrets.token_urlsafe(24)


def docker(*args, check=True):
    result = subprocess.run(['docker', *args], text=True, capture_output=True)
    if check and result.returncode:
        raise AssertionError(f'Docker {args[0]} failed: {result.stderr}')
    return result.stdout.strip()


def request(base, path, data=None, method=None, cookie=None, token=None, expected=200):
    headers = {}
    if data is not None:
        headers['Content-Type'] = 'application/json'
    if cookie:
        headers['Cookie'] = cookie
    if token:
        headers['Authorization'] = 'Bearer ' + token
    req = urllib.request.Request(base + path, data=None if data is None else json.dumps(data).encode(), headers=headers, method=method)
    try:
        response = urllib.request.urlopen(req, timeout=10)
    except urllib.error.HTTPError as error:
        response = error
    with response:
        assert response.status == expected, f'{path}: {response.status}, expected {expected}'
        body = response.read()
        return body, response.headers.get('Set-Cookie', '').split(';')[0]


def start(data):
    docker('run', '-d', '--name', name, '--network', name, '--network-alias', 'server', '--user', '1000:1000',
           '-p', '127.0.0.1::3000', '-p', '127.0.0.1::3001', '-e', 'ADMIN_PASSWORD=' + password,
           '-e', 'CADDY_ADMIN_URL=http://tls:2019', '-v', str(data) + ':/data', server_image)
    web = 'http://' + docker('port', name, '3000/tcp')
    api = 'http://' + docker('port', name, '3001/tcp')
    for _ in range(60):
        try:
            request(api, '/health')
            return web, api
        except (OSError, AssertionError):
            time.sleep(1)
    raise AssertionError('Server never became ready')


def login(web):
    return request(web, '/admin/login', {'password': password})[1]


def pair(web, api, cookie, device):
    code = json.loads(request(web, '/admin/pairing', {}, cookie=cookie)[0])['code']
    payload = {'code': code, 'deviceId': device, 'deviceName': device}
    token = json.loads(request(api, '/v1/pair', payload)[0])['token']
    request(api, '/v1/pair', payload, expected=403)
    return token


try:
    docker('network', 'create', name)
    with tempfile.TemporaryDirectory(prefix='clipsync-ci-', ignore_cleanup_errors=True) as tmp:
        data = Path(tmp) / 'data'
        data.mkdir()
        subprocess.run(['sudo', 'chown', '1000:1000', str(data)], check=True)
        docker('run', '-d', '--name', name + '-tls', '--network', name, '--network-alias', 'tls', tls_image)
        modules = docker('exec', name + '-tls', 'caddy', 'list-modules')
        assert 'dns.providers.cloudflare' in modules
        web, api = start(data)
        assert b'ClipSync' in request(web, '/')[0]
        request(api, '/admin/settings', expected=404)
        request(api, '/v1/clipboard', expected=401)
        request(web, '/admin/settings', expected=401)
        cookie = login(web)
        request(web, '/admin/settings', {'publicUrl': 'https://sync.example.com:39443'}, cookie=cookie)
        sender = pair(web, api, cookie, 'mac-test-device')
        receiver = pair(web, api, cookie, 'android-test-device')
        ws = websocket.create_connection(api.replace('http:', 'ws:') + '/v1/events',
                                         header={'Authorization': 'Bearer ' + receiver}, suppress_origin=True, timeout=10)
        assert json.loads(ws.recv())['item'] is None
        item = {'id': 'clip-ci', 'text': 'instant delivery', 'timestamp': 1000,
                'deviceId': 'mac-test-device', 'deviceName': 'mac-test-device', 'contentType': 'text'}
        request(api, '/v1/clipboard', item, method='PUT', token=sender)
        assert json.loads(ws.recv())['item'] == item
        ws.close()
        # Validate the actual DNS-only TLS config without obtaining certificates or contacting DNS.
        code = "import {caddyConfig} from './src/server.js'; console.log(JSON.stringify(caddyConfig({publicUrl:'https://sync.example.com:39443',cloudflareToken:'a'.repeat(40)})))"
        config = docker('exec', '-w', '/app', name, 'node', '--input-type=module', '-e', code)
        path = Path(tmp) / 'caddy-test.json'
        path.write_text(config)
        docker('cp', str(path), name + '-tls:/tmp/caddy-test.json')
        docker('exec', name + '-tls', 'caddy', 'validate', '--config', '/tmp/caddy-test.json')
        # Server and Caddy can communicate on the private network; WAN has no admin route.
        state = json.loads(request(web, '/admin/settings', cookie=cookie)[0])
        assert 'disabled' in state['tlsStatus'].lower(), state['tlsStatus']
        docker('rm', '-f', name)
        web, api = start(data)
        assert json.loads(request(api, '/v1/clipboard', token=receiver)[0]) == item
        ws = websocket.create_connection(api.replace('http:', 'ws:') + '/v1/events',
                                         header={'Authorization': 'Bearer ' + receiver}, suppress_origin=True, timeout=10)
        assert json.loads(ws.recv())['item'] == item
        ws.close()
        cookie = login(web)
        request(web, '/admin/devices/android-test-device', method='DELETE', cookie=cookie)
        request(api, '/v1/clipboard', token=receiver, expected=401)
        print('PASS: pairing, push, reconnect, persistence, revocation, isolated admin, DNS-only TLS configuration')
finally:
    docker('rm', '-f', name, name + '-tls', check=False)
    docker('network', 'rm', name, check=False)
    if 'tmp' in globals() and Path(tmp).exists():
        subprocess.run(['sudo', 'chown', '-R', f'{os.getuid()}:{os.getgid()}', tmp], check=True)
        shutil.rmtree(tmp)
