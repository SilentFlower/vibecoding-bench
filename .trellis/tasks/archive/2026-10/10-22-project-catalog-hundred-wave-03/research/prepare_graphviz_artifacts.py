"""从已留证的Debian12图形依赖镜像导出真实工具、插件、依赖及版权。"""
from argparse import ArgumentParser
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
import tarfile

from docker import from_env
from docker.errors import NotFound


IMAGE = 'sha256:bab59cbe25eed818c6f0bc46dd9decc63d27c8daee46a37f6d638e97bd057a96'
SCRIPT = r'''
import hashlib,json,os,re,subprocess
binary=os.path.realpath('/usr/bin/dot')
plugins='/usr/lib/x86_64-linux-gnu/graphviz'
paths={'dot':binary,'config6a':plugins+'/config6a'}
for name in os.listdir(plugins):
 if re.fullmatch(r'libgvplugin_\w+\.so\.6',name):paths[name]=os.path.realpath(plugins+'/'+name)
for name,path in list(paths.items()):
 if name=='config6a':continue
 for soname,dependency in re.findall(r'^\s*(\S+) => (/\S+) \(',subprocess.check_output(['ldd',path],text=True),re.M):
  if soname not in {'libc.so.6','libm.so.6','libz.so.1','libpthread.so.0','libdl.so.2','librt.so.1'}:
   paths[soname]=os.path.realpath(dependency)
rows=[]
for name,path in paths.items():
 package=None
 for candidate in [path,path.replace('/lib/','/usr/lib/',1),path.replace('/usr/lib/','/lib/',1)]:
  result=subprocess.run(['dpkg-query','-S',candidate],capture_output=True,text=True)
  if result.returncode==0:package=result.stdout.split(': ',1)[0];break
 if name=='config6a':package='libgvc6'
 if package is None:raise RuntimeError('unowned dependency: '+path)
 info=subprocess.check_output(['dpkg-query','-W','-f=${Version}\n${source:Package}\n${source:Version}',package],text=True).splitlines()
 raw=open(path,'rb').read()
 rows.append({'name':name,'source_path':path,'sha256':hashlib.sha256(raw).hexdigest(),'size':len(raw),'package':package,'version':info[0],
  'source_package':info[1],'source_version':info[2],'copyright':os.path.realpath('/usr/share/doc/'+package.split(':')[0]+'/copyright')})
print(json.dumps({'files':rows,'os_release':open('/etc/os-release').read()}))
'''


def read(container, path: str) -> bytes:
    """导出唯一普通原件。@param container 本次容器。@param path 已解析路径。@return 原字节。"""
    chunks, _ = container.get_archive(path)
    with tarfile.open(fileobj=BytesIO(b''.join(chunks))) as archive:
        members = archive.getmembers()
        if len(members) != 1 or not members[0].isfile():
            raise ValueError('制品只能是唯一普通文件')
        return archive.extractfile(members[0]).read()


def main() -> None:
    """保存依赖闭包，保持目标镜像不变；原生测试另作准入。@return None。"""
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('--attempt', type=int, default=1)
    options = parser.parse_args()
    output = Path('.deploy/project-catalog-hundred/stage-03') / ('graphviz-system-artifacts'
        if options.attempt == 1 else 'graphviz-system-artifacts-attempt-' + str(options.attempt).zfill(3))
    output.mkdir(parents=True, exist_ok=False)
    client, container = from_env(), None
    report = {'status': 'preparing', 'source_image': IMAGE, 'target_image_replaced': False,
        'real_model_calls': 0, 'source': '.deploy/github-100-research/resume-main/runtime-graphviz/Dockerfile'}
    artifacts, libraries, licenses = [], [], {}

    def save(relative: str, raw: bytes, executable: bool = False) -> dict:
        """保存本地普通制品及SHA。@param relative 路径。@param raw 原件。@param executable 执行位。@return 条目。"""
        target = output / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
        target.chmod(0o755 if executable else 0o644)
        row = {'path': 'artifacts/' + relative, 'digest': sha256(raw).hexdigest(), 'size': len(raw)}
        artifacts.append(row)
        return row

    try:
        container = client.containers.create(IMAGE, entrypoint=['python3', '-I', '-B', '-c'], command=[SCRIPT],
            user='1000:1000', network_mode='none', read_only=True, cap_drop=['ALL'],
            security_opt=['no-new-privileges'], mem_limit='128m', memswap_limit='128m', pids_limit=32,
            labels={'vibebench.verification': 'stage3-graphviz-artifacts'})
        container.start()
        if container.wait(timeout=45)['StatusCode'] != 0:
            raise RuntimeError(container.logs().decode()[-2000:])
        report.update(json.loads(container.logs(stdout=True, stderr=False)))
        for row in report['files']:
            raw = read(container, row['source_path'])
            if sha256(raw).hexdigest() != row['sha256']:
                raise ValueError('制品导出摘要变化')
            relative = ('graphviz-bin/' if row['name'] == 'dot' else 'graphviz-libs/') + row['name']
            artifact = save(relative, raw, row['name'] == 'dot')
            row['artifact'] = artifact['path']
            # 插件配置不是ELF库，保留为逐SHA制品，不能混入仅允许SONAME的库清单。
            if row['name'] not in ('dot', 'config6a'):
                libraries.append({'path': artifact['path'], 'sha256': artifact['digest']})
            package = row['package'].split(':')[0]
            if package not in licenses:
                licenses[package] = save('licenses/' + package + '-copyright', read(container, row['copyright']))
        for name in ('GPL-2', 'GPL-3', 'LGPL-2', 'LGPL-2.1', 'LGPL-3', 'GFDL-1.2', 'GFDL-1.3'):
            save('licenses/' + name, read(container, '/usr/share/common-licenses/' + name))
        manifest = json.dumps({'schema': 1, 'libraries': libraries}, indent=2).encode() + b'\n'
        row = save('graphviz-libs/manifest.json', manifest)
        executable = next(row for row in artifacts if row['path'] == 'artifacts/graphviz-bin/dot')
        report.update(status='prepared_pending_sources_and_target_validation', artifacts=artifacts, licenses=licenses,
            executables=[['dot', executable['path'], executable['digest']]],
            system_libraries=[row['path'], row['digest']])
    except Exception as error:
        report.update(status='error', error_type=type(error).__name__, message=str(error)[:2000])
        raise
    finally:
        if container is not None:
            identity = container.id
            container.remove(force=True)
            try:
                client.containers.get(identity)
            except NotFound:
                report['container_removed'] = True
        (output / 'provenance.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
        client.close()
    print(json.dumps({key: report[key] for key in ['status', 'executables', 'system_libraries', 'container_removed']}))


if __name__ == '__main__':
    main()
