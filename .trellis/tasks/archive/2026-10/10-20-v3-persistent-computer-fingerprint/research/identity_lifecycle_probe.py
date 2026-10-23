"""用独立控制端进程和两批本地镜像核对合成身份的持久性。"""
import argparse
import ipaddress
import json
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path

from docker import from_env
from docker.types import IPAMConfig, IPAMPool


REPOSITORY = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPOSITORY / 'deploy/v3'))
from manage import inspect_images


STAGE_SOURCE = '''import hashlib,json,os,shutil,sqlite3
from pathlib import Path
from docker import from_env
from account_runtime import AccountRuntime,atomic_json
from system_profile import verify_computer_profile

root=Path('/verify/data')
root.mkdir(exist_ok=True)
phase=os.environ['IDENTITY_VERIFY_PHASE']
def database():
    """连接仅含合成账号的持久数据库。@return SQLite 连接。"""
    connection=sqlite3.connect(root/'test.sqlite')
    connection.row_factory=sqlite3.Row
    return connection
if phase=='initial':
    with database() as connection:
        connection.execute('CREATE TABLE accounts(id INTEGER PRIMARY KEY,name TEXT,cc2api_account_id INTEGER)')
        connection.execute("INSERT INTO accounts VALUES(1,'synthetic',NULL)")
        connection.execute('CREATE TABLE runs(id TEXT PRIMARY KEY)')
account={'id':1,'name':'synthetic','upstream_proxy_scheme':'socks5',
    'upstream_socks5_host':os.environ['IDENTITY_VERIFY_PROXY'],'upstream_socks5_port':1080}
def fingerprint(timezone):
    """仅允许首次进程生成基础字段。@param timezone 时区。@return 合成基础画像。"""
    assert phase=='initial','恢复进程不能生成第二套基础身份'
    return {'profile_version':2,'hostname':'synthetic-fixed','machine_id':'a'*32,
        'mac':'02:00:00:00:00:73','tz':'America/Los_Angeles','lang':'en_US.UTF-8'}
runtime=AccountRuntime(from_env(),root,Path(os.environ['VERIFY_HOST_ROOT'])/'data',database,fingerprint,None)
try:
    row=runtime._row(account['name'],account['id'])
    state=Path('/verify/identity-snapshot.json')
    if phase=='initial':
        cached=runtime._root(row)/'cli/9.9.9'
        binary=cached/'node_modules/.bin/claude'
        binary.parent.mkdir(parents=True)
        shutil.copy2('/fixtures/mock_cli.py',binary)
        binary.chmod(0o755)
        (cached/'.ready').touch()
    before=json.loads(state.read_text()) if state.exists() else None
    if phase=='upgrade':
        runtime.maintenance(row['environment_id'],'rebuild')
    row,container=runtime.ensure(account,'9.9.9')
    home=runtime._root(row)/'home'
    marker=home/'persistent-marker'
    if phase=='initial':
        marker.write_bytes(b'synthetic persistent HOME')
        configuration=home/'.claude.json'
        atomic_json(configuration,{'userID':'synthetic-device-identity'})
        os.chown(configuration,1000,1000)
    saved=json.loads(row['fingerprint_json'])
    verify_computer_profile(container,saved['computer_profile'],saved['system_profile'])
    current={'fingerprint':saved,'container_id':container.id,
        'home':marker.read_text(),'device':json.loads((home/'.claude.json').read_text())}
    if before:
        assert all(current[key]==before[key] for key in ('fingerprint','home','device'))
        if phase=='restart':
            assert current['container_id']==before['container_id']
            runtime.maintenance(row['environment_id'],'stop')
            awake,container=runtime.ensure(account,'9.9.9')
            assert container.id==before['container_id'] and json.loads(awake['fingerprint_json'])==saved
        else:
            assert current['container_id']!=before['container_id']
    state.write_text(json.dumps(current))
    digest=hashlib.sha256(json.dumps(saved,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    print(json.dumps({'phase':phase,'static_sha256':digest,'identity_home_device':'passed',
        'dmi_content_access':'passed','image':container.image.id}),flush=True)
finally:
    runtime.stopping.set()
    runtime.heartbeat_pool.shutdown()
    runtime.client.close()
'''


def main() -> None:
    """运行首次创建、独立进程恢复、停止唤醒及镜像更新。

    :return: None；任一比较失败则非零退出，仅清理本次随机标签资源。
    """
    parser = argparse.ArgumentParser()
    parser.add_argument('--before-manifest', type=Path, required=True)
    parser.add_argument('--after-manifest', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    manifests = [json.loads(path.read_text()) for path in (args.before_manifest, args.after_manifest)]
    for path, manifest in zip((args.before_manifest, args.after_manifest), manifests):
        inspect_images({'V3_RELEASE_MANIFEST': str(path), **{
            'V3_' + role.upper() + '_IMAGE': manifest['images'][role]['reference'] for role in ('control', 'account')}})
    client = from_env()
    deployment = 'identity-verify-' + uuid.uuid4().hex[:12]
    labels = {'vibebench.product': 'v3', 'vibebench.deployment': deployment}
    used = [ipaddress.ip_network(item['Subnet']) for existing in client.networks.list()
        for item in existing.attrs.get('IPAM', {}).get('Config') or [] if item.get('Subnet')]
    routes = json.loads(subprocess.check_output(['ip', '-j', 'route', 'show']))
    used.extend(ipaddress.ip_network(item['dst']) for item in routes if item.get('dst') not in (None, 'default'))
    subnet = next(str(candidate) for index in range(200, 250)
        for candidate in [ipaddress.ip_network(f'10.232.{index}.0/24')]
        if not any(candidate.overlaps(item) for item in used if item.version == 4))
    network = client.networks.create('vibebench-v3-' + deployment, internal=True, labels=labels,
        ipam=IPAMConfig(pool_configs=[IPAMPool(subnet=subnet)]))
    results = []
    try:
        with tempfile.TemporaryDirectory(prefix='v3-identity-lifecycle-') as temporary:
            root = Path(temporary)
            fixtures = REPOSITORY / 'deploy/v3/fixtures'
            subprocess.run(['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-days', '1',
                '-subj', '/CN=api.anthropic.com', '-addext', 'subjectAltName=DNS:api.anthropic.com',
                '-keyout', str(root / 'native-usage.key'), '-out', str(root / 'native-usage.crt')],
                check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            mock = client.containers.run(manifests[0]['images']['control']['reference'], ['/fixtures/mock_network.py'],
                entrypoint='python', detach=True, network=network.name, labels={**labels, 'vibebench.role': 'verification'},
                volumes={str(fixtures): {'bind': '/fixtures', 'mode': 'ro'},
                    str(root): {'bind': '/fixtures-data', 'mode': 'rw'}})
            mock.reload()
            proxy = mock.attrs['NetworkSettings']['Networks'][network.name]['IPAddress']
            for phase, manifest in (('initial', manifests[0]), ('restart', manifests[0]), ('upgrade', manifests[1])):
                output = client.containers.run(manifest['images']['control']['reference'], ['-c', STAGE_SOURCE],
                    entrypoint='python', remove=True, network=network.name, labels={**labels, 'vibebench.role': 'orchestrator'},
                    environment={'PYTHONPATH': '/app', 'V3_DEPLOYMENT_ID': deployment, 'V3_RELEASE': manifest['release'],
                        'V3_ACCOUNT_IMAGE': manifest['images']['account']['reference'], 'V3_NETWORK': network.name,
                        'V3_ACCOUNT_MEMORY': '1536m', 'V3_ACCOUNT_SWAP': '2048m', 'VERIFY_HOST_ROOT': str(root),
                        'IDENTITY_VERIFY_PHASE': phase, 'IDENTITY_VERIFY_PROXY': proxy},
                    volumes={str(fixtures): {'bind': '/fixtures', 'mode': 'ro'},
                        str(root): {'bind': '/verify', 'mode': 'rw'},
                        '/var/run/docker.sock': {'bind': '/var/run/docker.sock', 'mode': 'rw'}})
                results.append(json.loads(output.decode().strip().splitlines()[-1]))
                print('通过：' + phase + ' 的独立控制端进程', flush=True)
            assert len({value['static_sha256'] for value in results}) == 1
            args.output.write_text(json.dumps({'network': 'internal-local-mock', 'real_credentials': False,
                'results': results}, ensure_ascii=False, indent=2) + '\n')
            print(json.dumps({'result': 'passed', 'phases': len(results), 'output': str(args.output)}, ensure_ascii=False))
    finally:
        for container in client.containers.list(all=True, filters={'label': [
                'vibebench.product=v3', 'vibebench.deployment=' + deployment]}):
            container.remove(force=True)
        network.remove()
        client.close()


if __name__ == '__main__':
    main()
