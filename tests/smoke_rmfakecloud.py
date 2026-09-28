"""Run only on a disposable Docker test runner; never install an Umbrel app."""
import http.cookiejar
import json
import os
from pathlib import Path
import secrets
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
import uuid

import yaml


ROOT = Path(__file__).resolve().parents[1]
compose = yaml.safe_load((ROOT / 'livinduck-rmfakecloud/docker-compose.yml').read_text())
service = compose['services']['server']
name = 'rmfakecloud-ci-' + uuid.uuid4().hex[:10]
seed = secrets.token_hex(32)
account = {'email': 'ci@example.invalid', 'password': secrets.token_urlsafe(24)}
cookies = http.cookiejar.CookieJar()
browser = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cookies))
anonymous = urllib.request.build_opener()
base = ''


def docker(*args, check=True):
    return subprocess.run(['docker', *args], check=check, text=True, capture_output=True).stdout.strip()


def request(path, data=None, method=None, client=browser, bearer=None, expected=200):
    headers = {}
    if data is not None:
        headers['Content-Type'] = 'application/json'
    if bearer:
        headers['Authorization'] = 'Bearer ' + bearer
    req = urllib.request.Request(base + path,
                                 data=None if data is None else json.dumps(data).encode(),
                                 headers=headers, method=method)
    try:
        with client.open(req, timeout=10) as response:
            status, body = response.status, response.read()
    except urllib.error.HTTPError as error:
        status, body = error.code, error.read()
    assert status == expected, f'{path}: expected {expected}, got {status}'
    return body


def start(data_dir):
    global base
    env = {key: str(value).replace('${APP_SEED}', seed)
           for key, value in service['environment'].items()}
    args = ['run', '-d', '--name', name, '--user', service['user'],
            '-p', '127.0.0.1::3000', '-v', str(data_dir) + ':/data']
    for key, value in env.items():
        args.extend(['-e', key + '=' + value])
    docker(*args, service['image'])
    base = 'http://' + docker('port', name, '3000/tcp')
    for _ in range(60):
        try:
            request('/health', client=anonymous)
            return
        except (OSError, AssertionError):
            time.sleep(1)
    raise AssertionError('Service failed to become healthy')


try:
    docker('pull', service['image'])
    with tempfile.TemporaryDirectory(prefix='rmfakecloud-ci-') as temporary:
        data_dir = Path(temporary) / 'data'
        data_dir.mkdir()
        # Umbrel owns installed package data as UID/GID 1000:1000.
        subprocess.run(['sudo', 'chown', '1000:1000', str(data_dir)], check=True)
        start(data_dir)
        assert b'<html' in request('/').lower(), 'Missing browser UI'
        request('/document-storage/json/2/docs', client=anonymous, expected=401)
        request('/ui/api/login', account)
        request('/ui/api/folders', {'name': 'Persistence smoke test', 'parentId': ''})
        documents_before = request('/ui/api/documents')
        assert b'Persistence smoke test' in documents_before
        code = json.loads(request('/ui/api/newcode'))
        assert isinstance(code, str) and code, 'Missing pairing code'
        device_token = request('/token/json/2/device/new', {
            'code': code, 'deviceDesc': 'desktop-windows', 'deviceID': str(uuid.uuid4())
        }, client=anonymous).decode()
        assert device_token.count('.') == 2
        request('/token/json/2/user/new', method='POST', client=anonymous, bearer=device_token)
        docker('rm', '-f', name)
        start(data_dir)
        # Existing browser cookie and device token must survive recreation.
        assert b'Persistence smoke test' in request('/ui/api/documents')
        request('/token/json/2/user/new', method='POST', client=anonymous, bearer=device_token)
        cookies.clear()
        request('/ui/api/login', account)
        assert b'Persistence smoke test' in request('/ui/api/documents')
        request('/ui/api/login', {**account, 'password': 'wrong-password'},
                client=anonymous, expected=401)
        print('PASS: browser UI, first login, pairing, auth and recreation persistence')
        docker('rm', '-f', name)
        # Files belong to container UID 1000, which may differ from runner UID.
        subprocess.run(['sudo', 'chown', '-R', f'{os.getuid()}:{os.getgid()}', temporary], check=True)
finally:
    docker('rm', '-f', name, check=False)
