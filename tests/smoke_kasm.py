"""Full disposable Kasm install through its wizard; never run against a NAS app."""
import json
import os
from pathlib import Path
import secrets
import subprocess
import tempfile
import threading
import time
import urllib.error
import urllib.request
import uuid

import socketio
import yaml

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / 'livinduck-kasm'
services = yaml.safe_load((APP / 'docker-compose.yml').read_text())['services']
prefix = 'kasm-ci-' + uuid.uuid4().hex[:10]
server, gateway, network = prefix + '-server', prefix + '-gateway', prefix
base = ''
admin_password = secrets.token_urlsafe(24)
user_password = secrets.token_urlsafe(24)


def docker(*args, check=True):
    result = subprocess.run(['docker', *args], capture_output=True, text=True)
    if check and result.returncode:
        raise RuntimeError(f'Docker command failed: {args[0]}: {result.stderr}')
    return result.stdout.strip()


def request(path):
    with urllib.request.urlopen(base + path, timeout=15) as response:
        return response.read().decode()


def wait_ready(path='/setup/'):
    for _ in range(120):
        try:
            if '<html' in request(path).lower():
                docker('exec', server, 'docker', 'info')
                return
        except (OSError, RuntimeError):
            pass
        time.sleep(2)
    raise AssertionError('Wizard or nested Docker failed to start')


def query(sql):
    return docker('exec', server, 'docker', 'exec', 'kasm_db', 'psql', '-U', 'kasmapp',
                  '-d', 'kasm', '-v', 'ON_ERROR_STOP=1', '-Atc', sql)


def start(data):
    docker('run', '-d', '--name', server, '--network', network,
        '--network-alias', 'livinduck-kasm_server_1', '--privileged',
        '-e', 'KASM_PORT=39402', '-e', 'SUBFOLDER=/setup/', '--stop-timeout', '90',
        '--entrypoint', 'python3',
        '-v', str(data / 'opt') + ':/opt',
        '-v', str(data / 'profiles') + ':/profiles',
        '-v', str(data / 'start.py') + ':/umbrel-start.py:ro',
        services['server']['image'], '/umbrel-start.py')


def install():
    done = threading.Event()
    landing = threading.Event()
    terminal = []
    client = socketio.Client(request_timeout=30)
    @client.on('renderinstall')
    def render_install(data):
        assert data[3] == '1.19.0'
        landing.set()
    @client.on('term')
    def term(data):
        terminal.append(data)
    @client.on('done')
    def complete(data):
        done.set()
    try:
        client.connect(base, socketio_path='setup/socket.io', transports=['websocket'])
        for _ in range(30):
            client.emit('renderlanding')
            if landing.wait(2):
                break
        assert landing.is_set(), 'Installer metadata missing'
        print('Starting full Kasm installation (no desktop image downloads).', flush=True)
        # Exercise the browser wizard's real installer, with disposable accounts.
        client.emit('install', [{'adminPass': admin_password, 'userPass': user_password,
                                'forceGpu': 'disabled'}, False])
        for _ in range(150):
            if done.wait(10):
                break
            if 'An error has occurred, please review the log' in ''.join(terminal):
                break
        if not done.is_set():
            output = ''.join(terminal)[-18000:]
            for password in (admin_password, user_password):
                output = output.replace(password, '[redacted]')
            print(output, flush=True)
            raise AssertionError('Kasm installer did not report success within 25 minutes')
    finally:
        client.disconnect()
    print('Kasm installer completed.', flush=True)


def check_app():
    for _ in range(120):
        try:
            if json.loads(request('/umbrel-health')).get('ok') is True:
                break
        except (OSError, ValueError):
            pass
        time.sleep(3)
    else:
        raise AssertionError('Kasm HTTPS API never became healthy')
    html = request('/')
    assert '<html' in html.lower()
    assert 'socket.io/socket.io.js' not in html, 'Root still shows the installer'
    assert 'Open Kasm' not in html, 'Root still shows the old launcher'
    assert query("SELECT proxy_port FROM zones WHERE zone_name='default';") == '0'
    # The browser API is reached through the same gateway as the UI.
    # Never log its credential-bearing response.
    def login(password):
        payload = json.dumps({'username': 'admin@kasm.local', 'password': password}).encode()
        req = urllib.request.Request(base + '/api/authenticate', data=payload,
                                     headers={'Content-Type': 'application/json'})
        try:
            with urllib.request.urlopen(req, timeout=15) as response:
                return json.load(response)
        except urllib.error.HTTPError:
            return {}
    auth = login(admin_password)
    assert auth.get('session_token'), f'Login failed; response keys: {list(auth)}'
    assert not login('invalid-password').get('session_token'), 'Wrong password accepted'


with tempfile.TemporaryDirectory(prefix=prefix) as temporary:
    data = Path(temporary)
    try:
        for service in ('server', 'gateway'):
            docker('pull', services[service]['image'])
        for directory in ('opt', 'profiles'):
            (data / directory).mkdir()
            subprocess.run(['sudo', 'chown', '1000:1000', str(data / directory)], check=True)
        env = dict(os.environ, APP_LIVINDUCK_KASM_DOLLAR='$')
        for source, target in [('nginx.conf.template', 'nginx.conf'), ('start.py.template', 'start.py')]:
            rendered = subprocess.run(['envsubst'], input=(APP / source).read_text(),
                text=True, capture_output=True, env=env, check=True).stdout
            (data / target).write_text(rendered)
        docker('network', 'create', network)
        start(data)
        docker('run', '-d', '--name', gateway, '--network', network,
            '-p', '127.0.0.1::8080',
            '-v', str(data / 'nginx.conf') + ':/etc/nginx/conf.d/default.conf:ro',
            '-v', str(data / 'opt') + ':/opt:ro', services['gateway']['image'])
        base = 'http://' + docker('port', gateway, '8080/tcp')
        wait_ready()
        assert 'socket.io' in request('/'), 'First launch did not open setup'
        wizard_js = request('/setup/public/js/index.js')
        assert 'location.assign("/");' in wizard_js
        assert 'location.reload(true);' not in wizard_js
        try:
            request('/umbrel-health')
        except urllib.error.HTTPError as error:
            assert error.code == 502
        else:
            raise AssertionError('Wizard alone was reported as a healthy Kasm')
        install()
        check_app()
        # Simulate the original package's persisted default zone and prove migration.
        query("UPDATE zones SET proxy_port=39402 WHERE zone_name='default';")
        docker('exec', server, 'sh', '-c', 'echo profile > /profiles/persistence-check')
        cert = docker('exec', server, 'sha256sum', '/opt/kasm/certs/kasm_wizard.crt')
        docker('stop', server)
        docker('rm', server)
        start(data)
        docker('restart', gateway)
        base = 'http://' + docker('port', gateway, '8080/tcp')
        wait_ready()
        check_app()
        assert cert == docker('exec', server, 'sha256sum', '/opt/kasm/certs/kasm_wizard.crt')
        assert docker('exec', server, 'cat', '/profiles/persistence-check') == 'profile'
        print('PASS: full wizard installation, WebSocket proxy, direct Kasm UI, API health, '
              'valid/rejected logins, default-zone migration and account/profile persistence', flush=True)
        print('NOT TESTED: Umbrel TLS/auth UI or streamed desktop sessions', flush=True)
    finally:
        docker('rm', '-f', gateway, check=False)
        docker('rm', '-f', server, check=False)
        docker('network', 'rm', network, check=False)
        subprocess.run(['sudo', 'chown', '-R', f'{os.getuid()}:{os.getgid()}', temporary], check=True)
