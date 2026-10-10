"""Disposable Docker integration checks. Never connects to the user's NAS or DNS."""
import json
import os
from pathlib import Path
import secrets
import shutil
from contextlib import contextmanager
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


@contextmanager
def disposable_directory():
    directory = tempfile.mkdtemp(prefix='clipsync-ci-')
    try:
        yield directory
    finally:
        docker('rm', '-f', name, name + '-tls', check=False)
        subprocess.run(['sudo', 'chown', '-R', f'{os.getuid()}:{os.getgid()}', directory], check=True)
        shutil.rmtree(directory)


try:
    docker('network', 'create', name)
    with disposable_directory() as tmp:
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
        if 'disabled' not in state['tlsStatus'].lower():
            print(docker('logs', name + '-tls'))
            diagnostic = "fetch('http://tls:2019/load',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({admin:{listen:'0.0.0.0:2019'}})}).then(async r=>console.log(r.status,await r.text())).catch(e=>console.log(e.message,e.cause?.code))"
            print(docker('exec', name, 'node', '-e', diagnostic))
            raise AssertionError(state['tlsStatus'])
        # Exercise the actual TLS listener and WebSocket proxy using an isolated
        # internal test CA. No public ACME request or real DNS credential is used.
        tls_check = """
import http from 'node:http';
import https from 'node:https';
import assert from 'node:assert/strict';
import {WebSocket} from 'ws';
import {caddyConfig} from './src/server.js';
const config=caddyConfig({publicUrl:'https://sync.example.com:39443',cloudflareToken:'a'.repeat(40)});
config.apps.tls.automation.policies[0].issuers=[{module:'internal'}];
await new Promise((resolve,reject)=>{
 const req=http.request('http://tls:2019/load',{method:'POST',headers:{'Content-Type':'application/json'}},res=>{res.resume();res.statusCode===200?resolve():reject(new Error('TLS test config '+res.statusCode));});
 req.on('error',reject);req.end(JSON.stringify(config));
});
const get=path=>new Promise((resolve,reject)=>{
 const req=https.request({hostname:'tls',port:8443,servername:'sync.example.com',path,headers:{Host:'sync.example.com:39443'},rejectUnauthorized:false},res=>{res.resume();resolve(res.statusCode);});
 req.on('error',reject);req.end();
});
let healthy=false;
for(let attempt=0;attempt<30;attempt++){try{healthy=(await get('/health'))===200;if(healthy)break;}catch{}await new Promise(r=>setTimeout(r,500));}
assert.equal(healthy,true);
assert.equal(await get('/admin/settings'),404);
const socket=new WebSocket('wss://tls:8443/v1/events',{servername:'sync.example.com',rejectUnauthorized:false,headers:{Host:'sync.example.com:39443',Authorization:'Bearer '+TOKEN}});
await new Promise((resolve,reject)=>{
 const timer=setTimeout(()=>reject(new Error('TLS WebSocket timeout')),10000);
 socket.once('message',data=>{try{assert.equal(JSON.parse(data).item.id,'clip-ci');clearTimeout(timer);resolve();}catch(e){reject(e);}});
 socket.once('error',reject);
});
socket.close();
console.log('PASS: dedicated-port HTTPS, admin isolation and WebSocket proxy');
""".replace('TOKEN', json.dumps(receiver))
        result = subprocess.run(['docker', 'exec', '-i', '-w', '/app', name, 'node', '--input-type=module'], input=tls_check, text=True, capture_output=True)
        assert result.returncode == 0, result.stderr
        print(result.stdout.strip())
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

