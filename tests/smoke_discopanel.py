"""Exercise the packaged services on a disposable Docker CI runner, never the NAS."""
import base64
import json
import os
from pathlib import Path
import secrets
import socket
import struct
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
import uuid

from playwright.sync_api import sync_playwright
import yaml


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / 'livinduck-discopanel'
BASE = 'http://127.0.0.1:18080'
PROJECT = 'discopanel-ci-' + uuid.uuid4().hex[:8]
TOKEN = ''
ACCOUNT = {'username': 'ci-admin', 'password': secrets.token_urlsafe(24)}
COMPOSE = []


def command(*args, check=True):
    result = subprocess.run(args, text=True, capture_output=True)
    if check and result.returncode:
        # Do not echo command arguments, which can include CI-only passwords.
        raise RuntimeError(result.stderr[-4000:])
    return result.stdout.strip()


def compose(*args, check=True):
    return command(*COMPOSE, *args, check=check)


def rpc(service, method, data=None, *, anonymous=False, expected=200):
    headers = {'Content-Type': 'application/json', 'Connect-Protocol-Version': '1'}
    if TOKEN and not anonymous:
        headers['Authorization'] = 'Bearer ' + TOKEN
    req = urllib.request.Request(
        BASE + '/discopanel.v1.' + service + '/' + method,
        data=json.dumps(data or {}).encode(), headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=120) as response:
            status, body = response.status, response.read()
    except urllib.error.HTTPError as error:
        status, body = error.code, error.read()
    assert status == expected, f'{service}/{method}: expected {expected}, got {status}: {body[:300]!r}'
    return json.loads(body or b'{}')


def wait_for(callback, description, seconds=120):
    deadline = time.monotonic() + seconds
    last = None
    while time.monotonic() < deadline:
        try:
            result = callback()
            if result:
                return result
        except (OSError, AssertionError, ValueError) as error:
            last = error
        time.sleep(2)
    raise AssertionError(f'Timed out waiting for {description}: {last}')


def varint(value):
    out = bytearray()
    while True:
        byte = value & 127
        value >>= 7
        out.append(byte | (128 if value else 0))
        if not value:
            return bytes(out)


def read_varint(conn):
    value = 0
    for offset in range(5):
        byte = conn.recv(1)
        if not byte:
            raise OSError('Minecraft closed connection')
        value |= (byte[0] & 127) << (offset * 7)
        if not byte[0] & 128:
            return value
    raise ValueError('Invalid Minecraft packet')


def minecraft_status():
    with socket.create_connection(('127.0.0.1', 25565), timeout=3) as conn:
        conn.settimeout(3)
        host = b'localhost'
        handshake = b'\x00' + varint(767) + varint(len(host)) + host + struct.pack('>H', 25565) + b'\x01'
        conn.sendall(varint(len(handshake)) + handshake + b'\x01\x00')
        read_varint(conn)
        assert read_varint(conn) == 0
        size = read_varint(conn)
        data = b''
        while len(data) < size:
            chunk = conn.recv(size - len(data))
            if not chunk:
                raise OSError('Incomplete Minecraft status')
            data += chunk
        result = json.loads(data)
        return result if 'players' in result and 'version' in result else None


def ready():
    return rpc('AuthService', 'GetAuthStatus', anonymous=True).get('localAuthEnabled')


def main():
    global COMPOSE, TOKEN
    with tempfile.TemporaryDirectory(prefix=PROJECT) as directory:
        temporary = Path(directory)
        seed = secrets.token_hex(32)
        text = (PACKAGE / 'docker-compose.yml').read_text()
        spec = yaml.safe_load(text.replace('${APP_DATA_DIR}', directory).replace('${APP_SEED}', seed))
        # Umbrel supplies app_proxy and container names. Test the real app
        # services; publish only a loopback UI port to the CI browser.
        proxy = spec['services'].pop('app_proxy')
        assert proxy['environment']['APP_HOST'] == 'livinduck-discopanel_engine_1'
        assert 'PROXY_AUTH_WHITELIST' not in proxy['environment']
        assert 'PROXY_AUTH_ADD' not in proxy['environment']
        for name, service in spec['services'].items():
            service['container_name'] = PROJECT + '-' + name
            for mount in service['volumes']:
                source = mount.split(':')[0]
                assert source.startswith(directory + '/data/')
                Path(source).mkdir(parents=True, exist_ok=True)
        spec['services']['engine']['ports'].append('127.0.0.1:18080:8080')
        path = temporary / 'compose.yml'
        path.write_text(yaml.safe_dump(spec, sort_keys=False))
        path.chmod(0o600)
        COMPOSE = ['docker', 'compose', '-p', PROJECT, '-f', str(path)]
        try:
            compose('config', '--quiet')
            compose('up', '-d', '--wait', '--wait-timeout', '180')
            wait_for(ready, 'panel startup')
            assert rpc('AuthService', 'GetAuthStatus', anonymous=True)['firstUserSetup']
            rpc('ServerService', 'ListServers', anonymous=True, expected=401)

            # Exercise the actual upstream first-use screen with JavaScript.
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch()
                page = browser.new_page()
                page.goto(BASE, wait_until='networkidle')
                page.get_by_placeholder('Choose admin username').fill(ACCOUNT['username'])
                page.get_by_placeholder('Choose a strong password').fill(ACCOUNT['password'])
                page.get_by_placeholder('Confirm your password').fill(ACCOUNT['password'])
                page.get_by_role('button', name='Create Admin Account').click()
                wait_for(lambda: not rpc('AuthService', 'GetAuthStatus', anonymous=True).get('firstUserSetup'),
                         'browser account creation')
                page.wait_for_url(lambda url: '/login' not in url, timeout=30000)
                assert page.locator('body').inner_text().strip()
                browser.close()
            print('PASS: native browser onboarding and unauthenticated access rejection')

            TOKEN = rpc('AuthService', 'Login', ACCOUNT, anonymous=True)['token']
            rpc('AuthService', 'Login', {**ACCOUNT, 'password': 'incorrect'}, anonymous=True, expected=401)
            rpc('AuthService', 'Register', {'username': 'uninvited', 'password': 'not-allowed'},
                anonymous=True, expected=403)
            servers = []
            for index in range(2):
                port = rpc('ServerService', 'GetNextAvailablePort')['port']
                assert port == 25565 + index
                server = rpc('ServerService', 'CreateServer', {
                    'name': f'CI world {index + 1}', 'mcVersion': '1.21.1',
                    'modLoader': 'MOD_LOADER_VANILLA', 'port': port,
                    'memory': 1536, 'maxPlayers': 3, 'dockerImage': 'java21',
                    'startImmediately': False,
                })['server']
                servers.append(server)
            server_id = servers[0]['id']
            rpc('ConfigService', 'UpdateServerConfig', {'serverId': server_id, 'updates': {
                'eula': 'TRUE', 'viewDistance': '3', 'simulationDistance': '3',
                'enableStatus': 'true', 'motd': 'DiscoPanel CI',
            }})
            marker = base64.b64encode(b'Persistent server data\n').decode()
            rpc('FileService', 'UpdateFile', {'serverId': server_id, 'path': 'ci-marker.txt', 'content': marker})
            rpc('ServerService', 'StartServer', {'id': server_id})
            wait_for(minecraft_status, 'real Minecraft server on the published game port', seconds=480)
            logs = rpc('ServerService', 'GetServerLogs', {'id': server_id, 'tail': 200})
            assert logs.get('logs'), 'Console logs unavailable'
            assert rpc('FileService', 'ListFiles', {'serverId': server_id}).get('files')
            print('PASS: two server definitions, Minecraft startup, game port, console and files')
            rpc('ServerService', 'StopServer', {'id': server_id})

            # Verify both services can be discarded: only bind-mounted data and
            # the same install seed survive, just as on an Umbrel app update.
            compose('down', '--timeout', '120')
            compose('up', '-d', '--wait', '--wait-timeout', '180')
            wait_for(ready, 'recreated panel')
            assert not rpc('AuthService', 'GetAuthStatus', anonymous=True).get('firstUserSetup')
            persisted = rpc('ServerService', 'ListServers')['servers']
            assert {s['id'] for s in persisted} == {s['id'] for s in servers}
            saved = rpc('FileService', 'GetFile', {'serverId': server_id, 'path': 'ci-marker.txt'})
            assert saved['content'] == marker
            TOKEN = rpc('AuthService', 'Login', ACCOUNT, anonymous=True)['token']
            rpc('ServerService', 'StartServer', {'id': server_id})
            wait_for(minecraft_status, 'Minecraft after engine recreation', seconds=180)
            rpc('ServerService', 'StopServer', {'id': server_id})
            assert (temporary / 'data/panel/discopanel.db').exists()
            assert not socket.socket().connect_ex(('127.0.0.1', 2375)) == 0, 'Unprotected engine API exposed'
            print('PASS: accounts, login, server files and game container survive full recreation')
        except Exception:
            # Auth manager can log a generated recovery key. Do not dump app logs.
            print(compose('ps', '--all', check=False))
            for line in compose('logs', '--no-color', '--tail', '100', 'server', check=False).splitlines():
                if any(phrase in line.lower() for phrase in (
                    'failed to create', 'failed to pull', 'error response from daemon',
                    'failed to start', 'failed to connect',
                )):
                    print(line.replace(seed, '[REDACTED]').replace(ACCOUNT['password'], '[REDACTED]'))
            raise
        finally:
            compose('down', '--timeout', '120', check=False)
            # Nested-engine files belong to container UIDs. Dispose only CI data.
            command('sudo', 'rm', '-rf', str(temporary / 'data'))


if __name__ == '__main__':
    main()
