"""使用合成AT和断网容器验证固定AGY就绪、共享映像、换代及进程故障收口。"""
import argparse
import json
import os
import shutil
import sys
import tempfile
import time
import uuid
from pathlib import Path

from source_layout import source_path

# 使用监督器既有请求上限，覆盖换代时的旧进程收尾和新进程准备。
PREPARE_SECONDS = 120


def _failure_evidence(container, phase: str, generation: int) -> dict:
    """收集固定合成探针的白名单证据。@param container 本次容器。@param phase 等待阶段。@param generation 合成代次。@return 有界脱敏摘要。"""
    result = {'event': 'agy-probe-failure', 'phase': phase, 'credential_generation': generation,
        'capture_failed': []}
    try:
        container.reload()
        state = container.attrs.get('State', {})
        result['state'] = {key: state.get(key) if type(state.get(key)) is kind else None
            for key, kind in [('Running', bool), ('OOMKilled', bool), ('ExitCode', int)]}
    except Exception:
        result['capture_failed'].append('state')
    try:
        counts, codes = {}, {}
        # 只保留协议分类；异常正文、凭据、身份和完整原生日志均不进入公开摘要。
        for line in container.logs(tail=32)[-32768:].splitlines():
            try:
                value = json.loads(line)
            except (ValueError, UnicodeError):
                continue
            if not isinstance(value, dict):
                continue
            kind = value.get('type')
            kind = kind if kind in ('supervisor_ready', 'prepared', 'job_finalized', 'status',
                'error', 'rejected', 'worker_error', 'shutdown_complete') else 'other'
            counts[kind] = counts.get(kind, 0) + 1
            if kind in ('error', 'rejected', 'worker_error'):
                code = value.get('code')
                code = code if code in ('worker_start_failed', 'request_deadline_exceeded',
                    'worker_capacity_deadline', 'supervisor_execution_failed', 'invalid_submission',
                    'invalid_supervisor_input', 'supervisor_closed') else 'other'
                codes[code] = codes.get(code, 0) + 1
        result.update(event_counts=counts, error_codes=codes)
    except Exception:
        result['capture_failed'].append('events')
    code = r'''import json,os
from itertools import islice
from pathlib import Path
result={'processes':{},'memory_events':{},'stages':{},'startup_errors':{}}
for path in list(Path('/proc').iterdir()):
    if not path.name.isdigit():continue
    try:
        with (path/'cmdline').open('rb') as stream:args=stream.read(4096).split(b'\x00')
        try:exe=os.readlink(path/'exe')
        except OSError:exe=''
        role=('supervisor' if b'agy_runtime.supervisor' in args else 'kernel' if b'agy_runtime.kernel' in args
            else 'observer' if exe.endswith('/observer-c') or args[0].endswith(b'/observer-c')
            else 'native' if exe.startswith('/memfd:agy-native-runtime') else 'other')
        result['processes'][role]=result['processes'].get(role,0)+1
    except OSError:continue
for name in ('memory.events','memory/memory.failcnt'):
    try:
        text=(Path('/sys/fs/cgroup')/name).read_text()
        if name.endswith('failcnt'):result['memory_events']['failcnt']=int(text)
        else:
            for line in text.splitlines():
                key,value=line.split()
                if key in ('oom','oom_kill','max'):result['memory_events'][key]=int(value)
    except (OSError,ValueError):continue
for name,pattern in [('worker_config','*/config.json'),('kernel_lock','*/state/kernel.lock'),('kernel_error','*/state/kernel-error.log'),('input_pipe','*/state/workers/*/*/input.pipe'),('listener_identity','*/state/workers/*/listener-identity.json')]:
    result['stages'][name]=sum(1 for _ in islice(Path('/state/root/workers').glob(pattern),256))
for path in islice(Path('/state/root/workers').glob('*/state/kernel-error.log'),256):
    try:
        with path.open('rb') as stream:
            stream.seek(max(0,os.fstat(stream.fileno()).st_size-8192));lines=stream.read(8192).decode(errors='replace').splitlines()
        for line in lines:
            kind=line.split(':',1)[0]
            if kind in ('RuntimeError','ValueError','PermissionError','FileNotFoundError','TimeoutError','OSError'):
                result['startup_errors'][kind]=result['startup_errors'].get(kind,0)+1
            for message,reason in [('RuntimeError: 原生观察器握手失败','observer_handshake_failed'),('RuntimeError: native_listener_identity_timeout','native_listener_identity_timeout'),('ValueError: image_decode_failed','image_decode_failed')]:
                if line==message:result['startup_errors'][reason]=result['startup_errors'].get(reason,0)+1
    except OSError:continue
print(json.dumps(result))
'''
    try:
        probe = container.exec_run(['python3', '-c', code], user='1001:1001')
        if probe.exit_code != 0 or len(probe.output) > 8192:
            raise ValueError('诊断子进程失败')
        # 容器返回值也再次投影，避免诊断源码后续扩展时意外公开私有字段。
        value = json.loads(probe.output)
        result['runtime'] = {section: {key: number for key, number in value[section].items()
            if key in keys and type(number) is int and 0 <= number < 2**63}
            for section, keys in [('processes', ('supervisor', 'kernel', 'observer', 'native', 'other')),
                ('memory_events', ('oom', 'oom_kill', 'max', 'failcnt')),
                ('stages', ('worker_config', 'kernel_lock', 'kernel_error', 'input_pipe', 'listener_identity')),
                ('startup_errors', ('RuntimeError', 'ValueError', 'PermissionError', 'FileNotFoundError',
                    'TimeoutError', 'OSError', 'observer_handshake_failed', 'native_listener_identity_timeout', 'image_decode_failed'))]}
    except Exception:
        result['capture_failed'].append('runtime')
    return result


def native_probe(image: str, *, crash: bool = False, image_package: bool = False) -> dict:
    """在明确镜像中执行零模型探针。@param image 已有测试镜像。@param crash 是否杀监督器。@param image_package 是否只使用镜像内包。@return 分项证据。"""
    import docker
    root=Path(__file__).resolve().parents[2]
    package=source_path(root,'orchestrator')
    temporary=Path(tempfile.mkdtemp(prefix='agy-native-offline-'))
    client=None
    container=connection=None
    phase,generation='launch',0
    try:
        client=docker.from_env(timeout=15)
        temporary.chmod(0o700)
        os.chown(temporary,1001,1001)
        config={'account_id':17,'environment_id':'synthetic-env','environment_generation':2,'max_workers':1,
            'binary_path':'/usr/local/bin/agy-1.5.9','work_root':'/state/root','proxy_url':''}
        path=temporary/'supervisor.json'
        path.write_text(json.dumps(config));path.chmod(0o600);os.chown(path,1001,1001)
        # PID1保留在容器内，监督器异常退出后仍能独立观察worker及Go进程的终止。
        wrapper="import subprocess,time; subprocess.Popen(['python3','-m','agy_runtime.supervisor','--config','/state/supervisor.json']); time.sleep(600)"
        mounts={str(temporary):{'bind':'/state','mode':'rw'}}
        if not image_package:
            mounts.update({str(package/'agy_runtime'):{'bind':'/opt/orchestrator/agy_runtime','mode':'ro'},
                str(package/'runtime_files.py'):{'bind':'/usr/local/bin/runtime_files.py','mode':'ro'}})
        container=client.containers.run(image,['-c',wrapper],entrypoint=['python3'],detach=True,stdin_open=True,
            user='1001:1001',network_mode='none',read_only=True,cap_drop=['ALL'],security_opt=['no-new-privileges:true'],
            mem_limit='768m',pids_limit=256,tmpfs={'/tmp':'rw,nosuid,nodev,noexec,size=128m'},
            environment={'PYTHONPATH':'/opt/v3/python:/usr/local/bin' if image_package else '/opt/orchestrator:/usr/local/bin'},
            volumes=mounts,labels={'vibebench.test-task':'agy-account-runtime'})
        connection=container.attach_socket(params={'stdin':True,'stream':True});connection._sock.settimeout(3)
        def send(value):
            connection._sock.sendall((json.dumps(value)+'\n').encode())
        def events():
            result=[]
            for line in container.logs().splitlines():
                try:result.append(json.loads(line))
                except ValueError:continue
            return result
        def wait(kind, request=None, timeout=50):
            nonlocal phase
            phase=kind
            until=time.monotonic()+timeout
            while time.monotonic()<until:
                for event in events():
                    if event.get('type')==kind and (request is None or event.get('request_id')==request):return event
                    if event.get('type') in ('error','rejected','worker_error'):raise ValueError('固定AGY断网准备失败')
                time.sleep(.1)
            raise ValueError('固定AGY断网探针超时')
        wait('supervisor_ready')
        ready=[];prepare_seconds=[]
        for generation in (1,2):
            request=str(uuid.uuid4())
            started=time.monotonic()
            send({'schema_version':1,'type':'prepare','request_id':request,'account_id':17,'environment_id':'synthetic-env',
                'environment_generation':2,'api_token_id':4,'credential_snapshot':{'account_id':17,'credential_generation':generation,
                    'access_token':'synthetic-offline-'+str(generation),'expires_at':4070908800000,'email':'synthetic@example.test'},
                'model':'gemini-synthetic','native_model':'MODEL_PLACEHOLDER_M36','body':{},'deadline_unix_ms':int((time.time()+PREPARE_SECONDS)*1000)})
            ready.append(wait('prepared',request,timeout=PREPARE_SECONDS+5)['native'])
            prepare_seconds.append(round(time.monotonic()-started,3))
            wait('job_finalized',request)
        request=str(uuid.uuid4());send({'schema_version':1,'type':'status','request_id':request})
        status=wait('status',request)['status']
        if status['image_decode_calls']!=1 or status['workers']!=1 or status['active']!=0:
            raise ValueError('AGY共享映像或物理并发不符合冻结配置')
        processes=[status['controller']['pid'],status['processes'][0]['controller']['pid'],ready[-1]['observer_pid'],ready[-1]['native_pid']]
        if crash:
            result=container.exec_run(['kill','-KILL',str(processes[0])],user='1001:1001')
            if result.exit_code:raise ValueError('监督器故障注入失败')
        else:
            send({'schema_version':1,'type':'shutdown'})
        code="""import json,time
from pathlib import Path
pids=PIDS
until=time.monotonic()+15
def running(pid):
    try:return Path('/proc/'+str(pid)+'/stat').read_text().split(') ',1)[1][0]!='Z'
    except FileNotFoundError:return False
while time.monotonic()<until and any(running(pid) for pid in pids):time.sleep(.1)
print(json.dumps({'terminated':not any(running(pid) for pid in pids)}))
""".replace('PIDS',repr(processes))
        result=container.exec_run(['python3','-c',code],user='1001:1001')
        terminated=result.exit_code==0 and json.loads(result.output)['terminated']
        if not terminated:raise ValueError('AGY物理进程收口未完成')
        count=sum(event.get('event',{}).get('type')=='model_start' for event in events())
        if count:raise ValueError('零模型准备出现模型入口')
        return {'passed':True,'evidence':'native_offline','package_source':'image' if image_package else 'source_mount',
            'network':'none','model_submissions':count,
            'source_sha256':ready[-1]['source_sha256'],'credential_generations':[1,2], 'image_scope':status['image_scope'],
            'prepare_seconds':prepare_seconds,'prepare_deadline_seconds':PREPARE_SECONDS,
            'image_bytes':status['image_bytes'],'image_decode_calls':status['image_decode_calls'],
            'controller':{key:value for key,value in status['controller'].items() if key!='pid'},
            'worker':[{name:{key:value for key,value in values.items() if key!='pid'} for name,values in process.items()
                if name in ('controller','native','observer') and values} for process in status['processes']],
            'cgroup_memory':status['cgroup_memory'],
            'crash':crash,'terminated':terminated}
    except Exception:
        if container:
            try:
                print(json.dumps(_failure_evidence(container,phase,generation)),file=sys.stderr,flush=True)
            except Exception:
                # 诊断本身失败时仍保留首个验证异常及后续容器清理。
                pass
        raise
    finally:
        original_error=sys.exception()
        cleanup_failed=[]
        # 独立尝试各项清理，保持首错，同时避免一次关闭异常跳过后续资源收口。
        for name, cleanup in [('connection', lambda: connection.close() if connection else None),
                ('container', lambda: container.remove(force=True) if container else None),
                ('state', lambda: shutil.rmtree(temporary)),
                ('client', lambda: client.close() if client else None)]:
            try:cleanup()
            except Exception:cleanup_failed.append(name)
        if cleanup_failed:
            try:
                print(json.dumps({'event':'agy-probe-cleanup-failure','steps':cleanup_failed}),file=sys.stderr,flush=True)
            except Exception:
                pass
            if original_error is None:raise ValueError('AGY探针清理失败')


def main() -> None:
    """执行明确测试镜像的断网固定内核验证。@return 无。"""
    parser=argparse.ArgumentParser()
    parser.add_argument('--native-image',required=True)
    parser.add_argument('--crash',action='store_true')
    parser.add_argument('--image-package',action='store_true')
    args=parser.parse_args()
    print(json.dumps(native_probe(args.native_image,crash=args.crash,image_package=args.image_package),ensure_ascii=False))


if __name__=='__main__':main()
