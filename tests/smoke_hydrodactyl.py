"""Test the package on disposable CI containers; never connect to the NAS."""
import hashlib
import os
from pathlib import Path
import secrets
import subprocess
import tempfile
import time
import uuid

from playwright.sync_api import sync_playwright
import yaml

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / 'livinduck-hydrodactyl'
BASE = 'http://127.0.0.1:18084'
PASSWORD = secrets.token_urlsafe(24)
COMPOSE = []


def compose(*args, input=None):
    result = subprocess.run([*COMPOSE, *args], input=input, text=True, capture_output=True)
    if result.returncode:
        raise RuntimeError(result.stderr[-3000:])
    return result.stdout.strip()


def php(source):
    return compose('exec', '-T', 'panel', 'php', input='''<?php
require '/app/vendor/autoload.php';
$app = require '/app/bootstrap/app.php';
$app->make(Illuminate\\Contracts\\Console\\Kernel::class)->bootstrap();
''' + source)


def wait_ready():
    deadline = time.monotonic() + 300
    while time.monotonic() < deadline:
        try:
            compose('exec', '-T', 'panel', 'curl', '-fsS', '-o', '/dev/null',
                    'http://127.0.0.1/auth/login')
            return
        except RuntimeError:
            time.sleep(3)
    raise AssertionError('Panel did not become ready within five minutes')


def login(page, password=PASSWORD):
    page.goto(BASE + '/auth/login')
    page.locator('input[name=user]').fill('ci-admin')
    page.locator('input[name=password]').fill(password)
    with page.expect_response(lambda r: r.url.endswith('/auth/login') and r.request.method == 'POST') as response:
        page.get_by_role('button', name='Sign in', exact=True).click()
    return response.value


def main():
    global COMPOSE
    package = yaml.safe_load((PACKAGE / 'docker-compose.yml').read_text())
    proxy = package['services'].pop('app_proxy')['environment']
    assert proxy['APP_HOST'] == 'livinduck-hydrodactyl_panel_1'
    assert proxy['PROXY_AUTH_WHITELIST'] == '/api/remote/*'
    assert 'PROXY_AUTH_ADD' not in proxy
    assert not any('ports' in service for service in package['services'].values())
    with tempfile.TemporaryDirectory(prefix='hydrodactyl-ci-') as tmp:
        data = Path(tmp)
        for name in ('database', 'cache', 'var', 'logs', 'uploads'):
            (data / 'data' / name).mkdir(parents=True)
        os.environ.update({
            'APP_DATA_DIR': tmp, 'APP_DOMAIN': 'localhost', 'NETWORK_IP': '172.16.0.0',
            'APP_LIVINDUCK_HYDRODACTYL_DB_PASSWORD': secrets.token_hex(32),
            'APP_LIVINDUCK_HYDRODACTYL_DB_ROOT_PASSWORD': secrets.token_hex(32),
            'APP_LIVINDUCK_HYDRODACTYL_REDIS_PASSWORD': secrets.token_hex(32),
        })
        # Only the disposable test exposes a raw panel port; Umbrel supplies its proxy.
        panel = package['services']['panel']
        panel['ports'] = ['127.0.0.1:18084:80']
        panel['environment']['APP_URL'] = BASE
        test_file = data / 'compose.yml'
        test_file.write_text(yaml.safe_dump(package, sort_keys=False))
        COMPOSE = ['docker', 'compose', '-p', 'hydrodactyl-ci-' + uuid.uuid4().hex[:8], '-f', str(test_file)]
        try:
            compose('up', '-d')
            wait_ready()
            with sync_playwright() as p:
                browser = p.chromium.launch()
                context = browser.new_context()
                page = context.new_page()
                page.goto(BASE)
                page.get_by_role('button', name='Get started', exact=True).click(timeout=30000)
                for field, value in {
                    'email': 'admin@example.com', 'username': 'ci-admin',
                    'name_first': 'CI', 'name_last': 'Admin',
                    'password': PASSWORD, 'password_confirmation': PASSWORD,
                }.items():
                    page.locator(f'input[name={field}]').fill(value)
                page.get_by_role('button', name='Continue', exact=True).click()
                with page.expect_response(lambda r: r.url.endswith('/setup') and r.request.method == 'POST') as response:
                    page.get_by_role('button', name='Create admin account', exact=True).click()
                assert response.value.status == 200, response.value.status
                page.wait_for_url(BASE + '/', timeout=30000)
                assert context.request.get(BASE + '/admin').status == 200
                assert context.request.get(BASE + '/setup').status == 404
                assert php('echo \\Pterodactyl\\Models\\User::count();') == '1'
                assert php('echo (int) \\Pterodactyl\\Models\\User::first()->root_admin;') == '1'
                assert context.request.get(BASE + '/api/remote/servers').status in (401, 403)
                anonymous = browser.new_context()
                assert anonymous.request.get(BASE + '/api/client', headers={'Accept': 'application/json'}).status == 401
                assert anonymous.request.get(BASE + '/setup').status == 404
                bad_page = anonymous.new_page()
                assert login(bad_page, 'wrong-password').status in (400, 401, 422)
                print('Browser onboarding, administrator access and unauthorized rejection passed', flush=True)
                # Save application-encrypted state, a real DB setting and an upload.
                php('''
app('Pterodactyl\\Contracts\\Repository\\SettingsRepositoryInterface')->set('settings::app:name', 'CI persisted panel');
file_put_contents('/app/var/ci-encrypted', app('encrypter')->encrypt('persistent-secret'));
file_put_contents('/app/storage/app/public/ci.txt', 'persistent-upload');
''')
                key_hash = hashlib.sha256(compose('exec', '-T', 'panel', 'cat', '/app/var/.env').encode()).hexdigest()
                for action in ('restart', 'recreate'):
                    if action == 'restart':
                        compose('restart')
                    else:
                        compose('down')
                        compose('up', '-d', '--force-recreate')
                    wait_ready()
                    assert hashlib.sha256(compose('exec', '-T', 'panel', 'cat', '/app/var/.env').encode()).hexdigest() == key_hash
                    assert php("echo app('encrypter')->decrypt(file_get_contents('/app/var/ci-encrypted'));") == 'persistent-secret'
                    assert php("echo config('app.name');") == 'CI persisted panel'
                    assert php('echo \\Pterodactyl\\Models\\User::count();') == '1'
                    fresh = browser.new_context()
                    assert login(fresh.new_page()).status == 200
                    assert fresh.request.get(BASE + '/admin').status == 200
                    assert fresh.request.get(BASE + '/setup').status == 404
                    assert fresh.request.get(BASE + '/storage/ci.txt').text() == 'persistent-upload'
                    fresh.close()
                    print(action + ': login, database, key, encrypted state and upload persisted', flush=True)
                browser.close()
            print('Hydrodactyl smoke test passed', flush=True)
        except Exception:
            # Logs can contain generated keys in upstream migration output. Do not publish them.
            print(compose('ps'), flush=True)
            raise
        finally:
            compose('down', '--volumes', '--remove-orphans')
            subprocess.run(['sudo', 'rm', '-rf', str(data / 'data')], check=True)


if __name__ == '__main__':
    main()
