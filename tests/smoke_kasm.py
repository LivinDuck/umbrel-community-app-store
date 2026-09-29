"""Disposable Docker CI: wizard/proxy, nested engine and storage persistence.

Does not accept the Kasm EULA, install inner Kasm services or launch a desktop.
Never run against an installed Umbrel app.
"""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
import uuid

import yaml

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / 'livinduck-kasm'
services = yaml.safe_load((APP / 'docker-compose.yml').read_text())['services']
prefix = 'kasm-ci-' + uuid.uuid4().hex[:10]
server, gateway, network = prefix + '-server', prefix + '-gateway', prefix
base = ''


def docker(*args, check=True):
    result = subprocess.run(['docker', *args], capture_output=True, text=True)
    if check and result.returncode:
        raise RuntimeError(f'Docker command failed: {args[0]}: {result.stderr}')
    return result.stdout.strip()


def request(path, payload=None):
    req = urllib.request.Request(base + path,
        data=None if payload is None else payload.encode(),
        headers={'Content-Type': 'text/plain;charset=UTF-8'})
    with urllib.request.urlopen(req, timeout=15) as response:
        return response.read().decode()


def wait_ready():
    for _ in range(120):
        try:
            if '<html' in request('/').lower():
                docker('exec', server, 'docker', 'info')
                return
        except (OSError, RuntimeError):
            pass
        time.sleep(2)
    print(docker('logs', '--tail', '60', gateway, check=False), flush=True)
    print(docker('logs', '--tail', '60', server, check=False), flush=True)
    raise AssertionError('Wizard or nested Docker failed to start')


def check_wizard():
    assert 'Open Kasm' in request('/umbrel')
    assert '39402' in request('/umbrel')
    assert 'socket.io' in request('/')
    assert 'renderinstall' in request('/public/js/index.js')
    # Exercise the real Socket.IO polling transport through the HTTPS bridge.
    route = '/socket.io/?EIO=4&transport=polling'
    handshake = request(route)
    assert handshake.startswith('0'), handshake[:100]
    sid = json.loads(handshake[1:])['sid']
    route += '&sid=' + sid
    request(route, '40')
    assert '40' in request(route)
    # The upstream wizard loads license/registry metadata asynchronously.
    for _ in range(30):
        request(route, '42["renderlanding"]')
        reply = request(route)
        if 'renderinstall' in reply and '1.19.0' in reply and 'LICENSE' in reply.upper():
            return
        if reply == '2':
            request(route, '3')
        time.sleep(2)
    raise AssertionError('Wizard did not return version and license for onboarding')


def start(data):
    docker('run', '-d', '--name', server, '--network', network,
        '--network-alias', 'livinduck-kasm_server_1', '--privileged',
        '-e', 'KASM_PORT=39402', '--stop-timeout', '90',
        '-v', str(data / 'opt') + ':/opt',
        '-v', str(data / 'profiles') + ':/profiles', services['server']['image'])


with tempfile.TemporaryDirectory(prefix=prefix) as temporary:
    data = Path(temporary)
    try:
        for service in ('server', 'gateway'):
            docker('pull', services[service]['image'])
        for directory in ('opt', 'profiles'):
            (data / directory).mkdir()
            subprocess.run(['sudo', 'chown', '1000:1000', str(data / directory)], check=True)
        # Mirror Umbrel's envsubst pass, including nginx dollar preservation.
        env = dict(os.environ, APP_LIVINDUCK_KASM_DOLLAR='$')
        for source, target in [('nginx.conf.template', 'nginx.conf'), ('index.html.template', 'index.html')]:
            rendered = subprocess.run(['envsubst'], input=(APP / source).read_text(),
                text=True, capture_output=True, env=env, check=True).stdout
            (data / target).write_text(rendered)
        docker('network', 'create', network)
        start(data)
        docker('run', '-d', '--name', gateway, '--network', network,
            '-p', '127.0.0.1::8080',
            '-v', str(data / 'nginx.conf') + ':/etc/nginx/conf.d/default.conf:ro',
            '-v', str(data / 'index.html') + ':/usr/share/nginx/html/index.html:ro',
            services['gateway']['image'])
        base = 'http://' + docker('port', gateway, '8080/tcp')
        wait_ready()
        check_wizard()
        cert = docker('exec', server, 'sha256sum', '/opt/kasm/certs/kasm_wizard.crt')
        docker('exec', server, 'docker', 'volume', 'create', 'persistence-check')
        docker('exec', server, 'sh', '-c',
            'echo retained > /opt/persistence-check; echo profile > /profiles/persistence-check')
        docker('stop', server)
        docker('rm', server)
        start(data)
        # Refresh nginx's upstream DNS after server container recreation.
        docker('restart', gateway)
        # Docker may allocate a new ephemeral host port on restart.
        base = 'http://' + docker('port', gateway, '8080/tcp')
        wait_ready()
        check_wizard()
        assert cert == docker('exec', server, 'sha256sum', '/opt/kasm/certs/kasm_wizard.crt')
        assert docker('exec', server, 'cat', '/opt/persistence-check') == 'retained'
        assert docker('exec', server, 'cat', '/profiles/persistence-check') == 'profile'
        docker('exec', server, 'docker', 'volume', 'inspect', 'persistence-check')
        # Disabling upstream's wizard must not break the package launch page.
        docker('exec', server, 'touch', '/opt/NO_WIZARD')
        docker('restart', server)
        assert 'Open Kasm' in request('/umbrel')
        print('PASS: launch page, HTTPS wizard proxy, Socket.IO onboarding metadata, '
              'nested Docker, writable mounts, certificates and recreation persistence')
        print('NOT TESTED: Umbrel auth/UI, Kasm account creation, inner services, desktop sessions')
    finally:
        docker('rm', '-f', gateway, check=False)
        docker('rm', '-f', server, check=False)
        docker('network', 'rm', network, check=False)
        subprocess.run(['sudo', 'chown', '-R', f'{os.getuid()}:{os.getgid()}', temporary], check=True)
