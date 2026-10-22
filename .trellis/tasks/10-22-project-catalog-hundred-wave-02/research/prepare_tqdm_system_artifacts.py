"""从已留证的Debian依赖镜像导出Tk依赖原件，不替换当前目标镜像。"""
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
import tarfile

from docker import from_env
from docker.errors import NotFound


DERIVED = 'sha256:7c48875a811ddc23a58b615f72f4772b54333c497cf28ab31df8b8729d93aa58'
SCRIPT = r'''
import hashlib,json,os,re,subprocess
binary='/usr/local/lib/python3.12/lib-dynload/_tkinter.cpython-312-x86_64-linux-gnu.so'
output=subprocess.check_output(['ldd',binary],text=True)
rows=[]
for name,path in re.findall(r'^\s*(\S+) => (/\S+) \(',output,re.M):
    if name in {'libc.so.6','libm.so.6','libz.so.1'}:
        continue
    real=os.path.realpath(path)
    package=None
    for candidate in [path,real,path.replace('/lib/','/usr/lib/',1),real.replace('/lib/','/usr/lib/',1)]:
        result=subprocess.run(['dpkg-query','-S',candidate],capture_output=True,text=True)
        if result.returncode==0:
            package=result.stdout.split(': ',1)[0]
            break
    if package is None:raise RuntimeError('unowned shared library: '+real)
    version=subprocess.check_output(['dpkg-query','-W','-f=${Version}',package],text=True)
    license_path=os.path.realpath('/usr/share/doc/'+package.split(':')[0]+'/copyright')
    data=open(real,'rb').read()
    rows.append({'soname':name,'path':real,'sha256':hashlib.sha256(data).hexdigest(),'size':len(data),
        'package':package,'version':version,'copyright_path':license_path})
print(json.dumps({'libraries':rows,'ldd':output,'os_release':open('/etc/os-release').read()}))
'''


def contents(container, path: str) -> bytes:
    """只读取已解析为普通文件的归档成员。@param container 本次容器。@param path 文件。@return 原字节。"""
    chunks, _ = container.get_archive(path)
    with tarfile.open(fileobj=BytesIO(b''.join(chunks)), mode='r:') as archive:
        members = archive.getmembers()
        if len(members) != 1 or not members[0].isfile():
            raise ValueError('系统依赖必须是唯一普通文件')
        return archive.extractfile(members[0]).read()


def main() -> None:
    """导出原件和各包版权，封存来源并确认清理。@return None。"""
    destination = Path('.deploy/project-catalog-hundred/stage-02/tqdm-system-artifacts')
    destination.mkdir(parents=True, exist_ok=False)
    client, container = from_env(), None
    report = {'status': 'running', 'source_image': DERIVED, 'real_model_calls': 0,
        'target_image_replaced': False, 'source': '.deploy/github-100-research/text-formats/tqdm/tk-system-image.json'}
    try:
        container = client.containers.create(DERIVED, entrypoint=['python3','-I','-c'], command=[SCRIPT],
            user='1000:1000', network_mode='none', read_only=True, cap_drop=['ALL'],
            security_opt=['no-new-privileges'], mem_limit='128m', memswap_limit='128m', pids_limit=32,
            labels={'vibebench.verification': 'tqdm-offline-system-artifacts'})
        container.start()
        result = container.wait(timeout=30)
        if result['StatusCode'] != 0:
            raise RuntimeError(container.logs().decode()[-2500:])
        report.update(json.loads(container.logs(stdout=True, stderr=False)))
        licenses = {}
        for row in report['libraries']:
            raw = contents(container, row['path'])
            if sha256(raw).hexdigest() != row['sha256']:
                raise ValueError('实际导出与容器来源摘要不同')
            path = destination / 'tk-libs' / row['soname']
            path.parent.mkdir(exist_ok=True)
            path.write_bytes(raw)
            row['artifact'] = 'artifacts/tk-libs/' + row['soname']
            package = row['package'].split(':')[0]
            if package not in licenses:
                raw = contents(container, row['copyright_path'])
                path = destination / 'licenses' / (package + '-copyright')
                path.parent.mkdir(exist_ok=True)
                path.write_bytes(raw)
                licenses[package] = {'artifact': 'artifacts/licenses/' + path.name,
                    'sha256': sha256(raw).hexdigest(), 'size': len(raw)}
        report.update(status='passed', licenses=licenses)
    finally:
        if container is not None:
            identity = container.id
            container.remove(force=True)
            try:
                client.containers.get(identity)
            except NotFound:
                report['container_removed'] = True
        (destination / 'provenance.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
        client.close()
    print(json.dumps({key:report[key] for key in ['status','source_image','container_removed']}))


if __name__ == '__main__':
    main()
