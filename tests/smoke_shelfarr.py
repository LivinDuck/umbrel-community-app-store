"""Exercise the packaged services on a disposable Docker runner, never a NAS."""
import html
import os
from pathlib import Path
import re
import secrets
import subprocess
import tempfile
import uuid

import requests
import yaml


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / 'livinduck-shelfarr'
password = 'Ci9-' + secrets.token_hex(16)
encrypted_value = secrets.token_hex(20)
project = 'shelfarr-ci-' + uuid.uuid4().hex[:10]
browser = requests.Session()
browser.headers['User-Agent'] = 'Mozilla/5.0 Chrome/130.0.0.0 Safari/537.36'


def run(*args):
    result = subprocess.run(args, text=True, capture_output=True)
    if result.returncode:
        raise RuntimeError(f'{args[0]} failed ({result.returncode}): {result.stderr}')
    return result.stdout.strip()


def csrf(response):
    response.raise_for_status()
    match = re.search(r'name="authenticity_token" value="([^"]+)"', response.text)
    assert match, 'Missing CSRF-protected form'
    return html.unescape(match.group(1))


with tempfile.TemporaryDirectory(prefix=project) as temporary:
    root = Path(temporary)
    root.chmod(0o755)
    config = yaml.safe_load((PACKAGE / 'docker-compose.yml').read_text())
    proxy = config['services'].pop('app_proxy')
    assert proxy['environment']['APP_HOST'] == 'livinduck-shelfarr_server_1'
    assert proxy['environment']['APP_PORT'] == 80
    assert 'PROXY_AUTH_ADD' not in proxy['environment']
    for name, service in config['services'].items():
        assert 'ports' not in service, 'Production must not bypass Umbrel auth'
        service['container_name'] = f'livinduck-shelfarr_{name}_1'
        volumes = []
        for volume in service['volumes']:
            volume = volume.replace('${APP_DATA_DIR}', str(root / 'app'))
            volume = volume.replace('${UMBREL_ROOT}', str(root / 'umbrel'))
            source = Path(volume.split(':')[0])
            source.mkdir(parents=True, exist_ok=True)
            run('sudo', 'chown', '1000:1000', str(source))
            volumes.append(volume)
        service['volumes'] = volumes
    # Only this disposable test exposes HTTP directly on loopback.
    config['services']['server']['ports'] = ['127.0.0.1::80']
    config_path = root / 'compose.yml'
    config_path.write_text(yaml.safe_dump(config))

    def compose(*args):
        return run('docker', 'compose', '-p', project, '-f', str(config_path), *args)

    def rails(code):
        return compose('exec', '-T', 'server', '/rails/bin/docker-entrypoint',
                       './bin/rails', 'runner', code)

    def start():
        compose('up', '-d', '--wait', '--wait-timeout', '240')
        return 'http://' + compose('port', 'server', '80')

    def fingerprints():
        return compose('exec', '-T', 'server', 'sha256sum',
                       '/rails/storage/.secret_key_base', '/rails/storage/.encryption_keys',
                       '/run/shelfarr-libation/token')

    def companion_status(authorized):
        # Execute as the actual app UID to verify shared-token readability too.
        command = 'curl -s -o /dev/null -w "%{http_code}" '
        if authorized:
            command += '-H "Authorization: Bearer $(cat /run/shelfarr-libation/token)" '
        command += 'http://livinduck-shelfarr_libation_1:8080/version'
        return compose('exec', '-T', '--user', '1000:1000', 'server', 'sh', '-c', command)

    try:
        compose('config', '--quiet')
        base = start()
        form = browser.get(base + '/', timeout=30)
        assert form.url.endswith('/sign_up'), 'First run must offer account creation'
        response = browser.post(base + '/sign_up', data={
            'authenticity_token': csrf(form), 'user[name]': 'CI Admin',
            'user[username]': 'ci_admin', 'user[password]': password,
            'user[password_confirmation]': password,
        }, timeout=60)
        response.raise_for_status()
        assert '/admin/settings' in response.url, 'Registration did not create administrator'
        assert browser.cookies.get('session_id'), 'Missing authenticated session'
        rails('raise unless Book.column_names.include?("bookorbit_id"); '
              'raise unless Book.column_names.include?("bookorbit_metadata"); '
              'raise unless SearchJob.enqueue_after_transaction_commit')
        response = browser.get(base + '/search', timeout=30)
        response.raise_for_status()
        assert '/search/orbit/app.js' in response.text, 'Custom search UI is missing'
        response = browser.get(base + '/search/orbit/app.js', timeout=30)
        response.raise_for_status()
        assert len(response.content) > 10000, 'Custom search assets missing'
        response = browser.get(base + '/search/orbit/source', timeout=30)
        response.raise_for_status()
        import io, tarfile
        with tarfile.open(fileobj=io.BytesIO(response.content), mode='r:gz') as archive:
            names = archive.getnames()
            assert 'orbit_search.rb' in names and 'LICENSE-BookOrbit' in names
            assert not any('credentials.json' in name or 'node_modules' in name for name in names)

        anonymous = requests.Session()
        anonymous.headers.update(browser.headers)
        response = anonymous.get(base + '/admin/settings', timeout=30)
        assert '/session/new' in response.url, 'Admin settings are publicly accessible'
        response = anonymous.get(base + '/sign_up', timeout=30)
        assert '/session/new' in response.url, 'Registration remains open after setup'
        response = anonymous.post(base + '/session', data={
            'authenticity_token': csrf(response), 'username': 'ci_admin',
            'password': 'IncorrectPassword9',
        }, timeout=30)
        assert '/session/new' in response.url and not anonymous.cookies.get('session_id')
        assert companion_status(False) == '401', 'Companion accepts unauthenticated requests'
        assert companion_status(True) == '200', 'Shared companion token does not work'
        rails(f'u = User.find_by!(username: "ci_admin"); raise unless u.admin?; '
              f'u.update!(otp_secret: "{encrypted_value}"); '
              'SettingsService.set(:audiobook_path_template, "ci/{author}/{title}")')
        compose('exec', '-T', '--user', '1000:1000', 'server', 'sh', '-c',
                'set -e; printf audiobook > /audiobooks/ci.txt; '
                'printf ebook > /ebooks/ci.txt; printf download > /downloads/ci.txt')
        compose('exec', '-T', '--user', '1000:1000', 'libation', 'sh', '-c',
                'set -e; printf backup > /data/ci.txt; printf state > /config/ci.txt')
        before = fingerprints()
        compose('down')
        base = start()
        assert fingerprints() == before, 'Generated keys changed after recreation'
        response = browser.get(base + '/admin/settings', timeout=30)
        response.raise_for_status()
        assert '/admin/settings' in response.url, 'Session did not survive recreation'
        rails(f'raise unless User.find_by!(username: "ci_admin").otp_secret == "{encrypted_value}"; '
              'raise unless SettingsService.get(:audiobook_path_template) == "ci/{author}/{title}"')
        for path, expected in [('/audiobooks/ci.txt', 'audiobook'), ('/ebooks/ci.txt', 'ebook'),
                               ('/downloads/ci.txt', 'download'), ('/imports/libation/ci.txt', 'backup')]:
            assert compose('exec', '-T', '--user', '1000:1000', 'server', 'cat', path) == expected
        assert compose('exec', '-T', '--user', '1000:1000', 'libation', 'cat', '/config/ci.txt') == 'state'
        assert companion_status(True) == '200'
        browser.cookies.clear()
        form = browser.get(base + '/session/new', timeout=30)
        response = browser.post(base + '/session', data={
            'authenticity_token': csrf(form), 'username': 'ci_admin', 'password': password,
        }, timeout=30)
        response.raise_for_status()
        assert browser.cookies.get('session_id'), 'Account login did not survive recreation'
        assert '/admin/settings' in browser.get(base + '/admin/settings', timeout=30).url
        print('PASS: onboarding, authentication, writable storage, companion and recreation persistence')
    finally:
        compose('down', '--volumes', '--remove-orphans')
        # Containers create private UID-1000 files; allow TemporaryDirectory cleanup.
        run('sudo', 'chown', '-R', f'{os.getuid()}:{os.getgid()}', str(root))
