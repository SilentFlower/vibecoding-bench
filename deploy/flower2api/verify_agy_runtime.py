"""使用合成AT和断网容器验证固定AGY就绪、共享映像、换代及进程故障收口。"""
import argparse
import json
import os
import shutil
import tempfile
import time
import uuid
from pathlib import Path

from source_layout import source_path


def native_probe(image: str, *, crash: bool = False) -> dict:
    """在明确镜像中执行零模型探针。@param image 已有测试镜像。@param crash 是否杀监督器。@return 分项证据。"""
    import docker
    root=Path(__file__).resolve().parents[2]
    package=source_path(root,'orchestrator')
    temporary=Path(tempfile.mkdtemp(prefix='agy-native-offline-'))
    client=docker.from_env(timeout=15)
    container=connection=None
    try:
        temporary.chmod(0o700)
        os.chown(temporary,1001,1001)
        config={'account_id':17,'environment_id':'synthetic-env','environment_generation':2,'max_workers':1,
            'binary_path':'/usr/local/bin/agy-1.5.9','work_root':'/state/root','proxy_url':''}
        path=temporary/'supervisor.json'
        path.write_text(json.dumps(config));path.chmod(0o600);os.chown(path,1001,1001)
        # PID1保留在容器内，监督器异常退出后仍能独立观察worker及Go进程的终止。
        wrapper="import subprocess,time; subprocess.Popen(['python3','-m','agy_runtime.supervisor','--config','/state/supervisor.json']); time.sleep(180)"
        container=client.containers.run(image,['-c',wrapper],entrypoint=['python3'],detach=True,stdin_open=True,
            user='1001:1001',network_mode='none',read_only=True,cap_drop=['ALL'],security_opt=['no-new-privileges:true'],
            mem_limit='768m',pids_limit=256,tmpfs={'/tmp':'rw,nosuid,nodev,noexec,size=128m'},
            environment={'PYTHONPATH':'/opt/orchestrator:/usr/local/bin'},
            volumes={str(package/'agy_runtime'):{'bind':'/opt/orchestrator/agy_runtime','mode':'ro'},
                str(package/'runtime_files.py'):{'bind':'/usr/local/bin/runtime_files.py','mode':'ro'},
                str(temporary):{'bind':'/state','mode':'rw'}},labels={'vibebench.test-task':'agy-account-runtime'})
        connection=container.attach_socket(params={'stdin':True,'stream':True});connection._sock.settimeout(3)
        def send(value):
            connection._sock.sendall((json.dumps(value)+'\n').encode())
        def events():
            result=[]
            for line in container.logs().splitlines():
                try:result.append(json.loads(line))
                except ValueError:continue
            return result
        def wait(kind, request=None):
            until=time.monotonic()+50
            while time.monotonic()<until:
                for event in events():
                    if event.get('type')==kind and (request is None or event.get('request_id')==request):return event
                    if event.get('type') in ('error','rejected','worker_error'):raise ValueError('固定AGY断网准备失败')
                time.sleep(.1)
            raise ValueError('固定AGY断网探针超时')
        wait('supervisor_ready')
        ready=[]
        for generation in (1,2):
            request=str(uuid.uuid4())
            send({'schema_version':1,'type':'prepare','request_id':request,'account_id':17,'environment_id':'synthetic-env',
                'environment_generation':2,'api_token_id':4,'credential_snapshot':{'account_id':17,'credential_generation':generation,
                    'access_token':'synthetic-offline-'+str(generation),'expires_at':4070908800000,'email':'synthetic@example.test'},
                'model':'gemini-synthetic','native_model':'MODEL_PLACEHOLDER_M36','body':{},'deadline_unix_ms':int((time.time()+45)*1000)})
            ready.append(wait('prepared',request)['native'])
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
        return {'passed':True,'evidence':'native_offline','network':'none','model_submissions':count,
            'source_sha256':ready[-1]['source_sha256'],'credential_generations':[1,2], 'image_scope':status['image_scope'],
            'image_bytes':status['image_bytes'],'image_decode_calls':status['image_decode_calls'],
            'controller':{key:value for key,value in status['controller'].items() if key!='pid'},
            'worker':[{name:{key:value for key,value in values.items() if key!='pid'} for name,values in process.items()
                if name in ('controller','native','observer') and values} for process in status['processes']],
            'cgroup_memory':status['cgroup_memory'],
            'crash':crash,'terminated':terminated}
    finally:
        if connection:connection.close()
        if container:container.remove(force=True)
        shutil.rmtree(temporary)


def main() -> None:
    """执行明确测试镜像的断网固定内核验证。@return 无。"""
    parser=argparse.ArgumentParser()
    parser.add_argument('--native-image',required=True)
    parser.add_argument('--crash',action='store_true')
    args=parser.parse_args()
    print(json.dumps(native_probe(args.native_image,crash=args.crash),ensure_ascii=False))


if __name__=='__main__':main()
