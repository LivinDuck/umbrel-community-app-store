#!/usr/bin/env python3
"""Disposable package test: setup, authentication, scan, and recreation persistence."""
import json, os, secrets, shutil, subprocess, tempfile, time, urllib.request, urllib.error, zipfile
from pathlib import Path
import yaml
ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / 'livinduck-bookorbit'

def main():
    with tempfile.TemporaryDirectory(prefix='bookorbit-smoke-') as tmp:
        work = Path(tmp)
        package = yaml.safe_load((APP / 'docker-compose.yml').read_text())
        package.pop('version', None)
        package['services'].pop('app_proxy')
        env = dict(os.environ, APP_DATA_DIR=tmp, DEVICE_DOMAIN_NAME='localhost', APP_PROXY_PORT='3000')
        for name in ['POSTGRES_PASSWORD','JWT_SECRET','SETUP_TOKEN','PODCAST_KEY','EMAIL_KEY','MIGRATION_KEY','BOOK_REQUEST_KEY','ADMIN_PASSWORD']:
            env['APP_LIVINDUCK_BOOKORBIT_' + name] = secrets.token_hex(32)
        for name in ['app','postgres','books','onboarding']:
            path = work / 'data' / name
            path.mkdir(parents=True)
            path.chmod(0o777)
        server = package['services']['server']
        server['environment']['POSTGRES_HOST'] = 'postgres'
        server['ports'] = ['127.0.0.1::3000']
        setup = package['services']['setup']
        setup['entrypoint'][2] = setup['entrypoint'][2].replace('livinduck-bookorbit_server_1', 'server')
        file = work / 'compose.yml'
        file.write_text(yaml.safe_dump(package, sort_keys=False))
        project = 'bookorbit-test-' + secrets.token_hex(4)
        def compose(*args, capture=False):
            return subprocess.run(['docker','compose','-p',project,'-f',str(file),*args], env=env, check=True, text=True, capture_output=capture)
        try:
            compose('up','-d', '--wait', '--wait-timeout', '240', 'server')
            compose('up','-d','setup')
            port = compose('port','server','3000',capture=True).stdout.strip().rsplit(':',1)[1]
            base = 'http://127.0.0.1:' + port + '/api/v1'
            def api(path, body=None, token=None, method=None):
                headers = {'Content-Type':'application/json'}
                if token: headers['Authorization'] = 'Bearer ' + token
                req = urllib.request.Request(base+path, data=json.dumps(body).encode() if body is not None else None, headers=headers, method=method)
                try:
                    with urllib.request.urlopen(req,timeout=20) as response:
                        raw=response.read(); return response.status, json.loads(raw) if raw else None
                except urllib.error.HTTPError as error:
                    return error.code, None
            deadline=time.monotonic()+90
            while time.monotonic()<deadline:
                status, data=api('/auth/setup-status')
                if status==200 and not data['needsSetup']: break
                time.sleep(2)
            else: raise AssertionError('bootstrap did not complete')
            password=compose('exec','-T','setup','cat','/onboarding/admin-password.txt',capture=True).stdout.strip()
            status, login=api('/auth/login',{'username':'admin','password':password})
            assert status in (200,201), ('login',status)
            token=login['accessToken']
            assert api('/libraries')[0]==401
            assert api('/auth/login',{'username':'admin','password':'Wrong-password-123'})[0]==401
            status,library=api('/libraries',{'name':'Smoke books','icon':'book','folders':['/books'],'watch':True,'organizationMode':'book_per_file','metadataPrecedence':['embedded','opfFile','nfoFile','sidecar','folderStructure']},token)
            assert status==201, ('library',status)
            library_id=library['id']
            with zipfile.ZipFile(work/'data/books/Smoke.epub','w') as z:
                z.writestr('mimetype','application/epub+zip')
                z.writestr('META-INF/container.xml','<?xml version="1.0"?><container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles><rootfile full-path="content.opf" media-type="application/oebps-package+xml"/></rootfiles></container>')
                z.writestr('content.opf','<?xml version="1.0"?><package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="id"><metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:identifier id="id">smoke-original</dc:identifier><dc:title>Original Smoke Book</dc:title><dc:creator>Package Test</dc:creator><dc:language>en</dc:language></metadata><manifest><item id="body" href="body.xhtml" media-type="application/xhtml+xml"/></manifest><spine><itemref idref="body"/></spine></package>')
                z.writestr('body.xhtml','<html xmlns="http://www.w3.org/1999/xhtml"><head><title>Test</title></head><body><p>Original test fixture.</p></body></html>')
            assert api(f'/scanner/libraries/{library_id}/scan',{},token)[0] in (200,201,202,409)
            body={'sort':[],'pagination':{'page':0,'size':200},'collapseSeries':False}
            deadline=time.monotonic()+90
            while time.monotonic()<deadline:
                status,books=api(f'/libraries/{library_id}/books',body,token)
                if status in (200,201) and 'Original Smoke Book' in json.dumps(books): break
                time.sleep(2)
            else: raise AssertionError('ebook scan failed')
            compose('up','-d','--force-recreate','--wait','--wait-timeout','240','server')
            compose('up','-d','--force-recreate','setup')
            port=compose('port','server','3000',capture=True).stdout.strip().rsplit(':',1)[1]
            base='http://127.0.0.1:'+port+'/api/v1'
            status,login=api('/auth/login',{'username':'admin','password':password})
            assert status in (200,201), ('persistent login',status)
            assert 'Original Smoke Book' in json.dumps(api(f'/libraries/{library_id}/books',body,login['accessToken'])[1])
            assert api('/auth/setup',{'username':'other','name':'Other','email':'other@example.com','password':'Other-password-123'})[0] not in (200,201)
            print('PASS: bootstrap, rejected unauthenticated access, library scan, recreation and login persistence')
        finally:
            compose('down','--volumes','--remove-orphans')
            # Containers may own data as a different UID. The CI runner has sudo.
            if shutil.which('sudo'): subprocess.run(['sudo','rm','-rf',str(work/'data')],check=True)

if __name__=='__main__': main()
