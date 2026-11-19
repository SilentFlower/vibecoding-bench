"""同宿主CLI文件写入下的真实原生sender性能对照。"""
import json
import os
import shutil
import time
import uuid
from pathlib import Path

from verify_forwarding import certificates


_SERVER = """import os,pathlib,subprocess,sys,threading
sys.path.insert(0,'/fixtures')
import forwarding_network as fixture
threading.Thread(target=fixture.main,daemon=True).start()
subprocess.run(['/usr/local/bin/account-sender'],env={**os.environ,'V3_SENDER_CONFIG':'/run/v3/sender.json','TOKIO_WORKER_THREADS':'2','RUST_LOG':'error'},check=True)
"""
_WRITE = """import json,os,pathlib,time
root=pathlib.Path('/tmp/claude-1000/performance');root.mkdir(parents=True,exist_ok=True)
start=time.monotonic();count=0;chunk=b'x'*(4*1024*1024)
while not pathlib.Path('/run/v3/scratchpad-perf-stop').exists() and time.monotonic()-start<45:
 tick=time.monotonic()
 with (root/('payload-'+str(count%4))).open('wb') as output:
  output.write(chunk);output.flush();os.fsync(output.fileno())
 count+=1
 temporary=root/'stats.tmp';temporary.write_text(json.dumps({'writes':count,'bytes':count*len(chunk)}));temporary.replace(root/'stats.json')
 time.sleep(max(0,.1-(time.monotonic()-tick)))
"""
_MEASURE = """import concurrent.futures,json,pathlib,time,urllib.error,urllib.request,uuid
def submit(index):
 marker='scratchpad-perf-'+str(index)+'-'+uuid.uuid4().hex
 request={'account_id':1,'environment_id':'fixture','generation':1,'request_id':str(uuid.uuid4()),
 'deadline_unix_ms':int(time.time()*1000)+90000,'method':'POST','target_url':'https://api.anthropic.com/v1/messages',
 'headers':[['content-type','application/json']],'preserve_header_casing':True}
 payload={'request':request,'input':{'schema_version':1,'request_id':request['request_id'],
 'body':{'model':'claude-sonnet-4-6','max_tokens':64,'stream':True,'messages':[{'role':'user','content':marker}]},'headers':[]},
 'bearer':'synthetic-bearer','device_id':'a'*64,'account_uuid':'11111111-1111-4111-8111-111111111111',
 'organization_uuid':'22222222-2222-4222-8222-222222222222','email':'fixture@example.invalid','concurrency':3,'log_mode':'info'}
 body=json.dumps(payload).encode();start=time.monotonic();first=None
 req=urllib.request.Request('http://127.0.0.1:8091/internal/native/messages',data=body,
 headers={'Authorization':'Bearer '+'f'*64,'Content-Type':'application/json'})
 try:response=urllib.request.urlopen(req,timeout=95)
 except urllib.error.HTTPError as error:raise ValueError(str(error.code)+':'+error.read(2000).decode()) from error
 with response:
  content=[]
  for line in response:
   content.append(line)
   if first is None and b'text_delta' in line:first=time.monotonic()-start
 text=b''.join(content)
 if first is None or marker.encode() not in text:raise ValueError('原生响应或归属错误')
 return {'latency_ms':(time.monotonic()-start)*1000,'ttft_ms':first*1000}
def cpu():
 rows=dict(line.split() for line in pathlib.Path('/sys/fs/cgroup/cpu.stat').read_text().splitlines())
 return int(rows['usage_usec'])
deadline=time.monotonic()+10
while True:
 try:
  with urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:8091/internal/status',headers={'Authorization':'Bearer '+'f'*64}),timeout=1):pass
  break
 except Exception:
  if time.monotonic()>deadline:raise
  time.sleep(.05)
cold=submit(-1)
with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:list(pool.map(submit,range(6)))
before=cpu();start=time.monotonic()
with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:rows=list(pool.map(submit,range(60)))
elapsed=time.monotonic()-start
print(json.dumps({'cold':cold,'rows':rows,'seconds':elapsed,'throughput':len(rows)/elapsed,'cpu_usec':cpu()-before}))
"""


def measure_sender_performance(client, image: str, root: Path, baseline, disk, controls: dict,
                               pairs: int = 6) -> dict:
    """在相同写入速率下交错运行真实原生sender和隔离HTTPS上游。

    :param client: 本地Docker客户端。
    :param image: 包含专用测试CA支持的账号镜像。
    :param root: 本次验证的私有数据目录。
    :param baseline: 使用原tmpfs的CLI。
    :param disk: 使用新磁盘挂载的CLI。
    :param controls: 两个CLI各自的宿主控制目录。
    :param pairs: 交错配对次数。
    :return: 原始请求延迟、吞吐、冷请求与容器CPU计量。
    """
    if client.images.get(image).attrs['Config'].get('Labels', {}).get('vibebench.verification') != 'extra-ca':
        raise ValueError('性能验证需要专用测试CA镜像')
    work = root / 'sender-performance'
    work.mkdir(mode=0o700)
    certificate_root = work / 'certificates'
    certificate_root.mkdir(mode=0o700)
    certificates(certificate_root)
    results = []
    for pair in range(pairs):
        for mode in (('tmpfs', 'disk') if pair % 2 == 0 else ('disk', 'tmpfs')):
            cli = baseline if mode == 'tmpfs' else disk
            control = controls[mode]
            stop = control / 'scratchpad-perf-stop'
            stop.unlink(missing_ok=True)
            writer = client.api.exec_create(cli.id, ['python3', '-I', '-c', _WRITE], user='1000:1000')['Id']
            client.api.exec_start(writer, detach=True)
            case = work / ('pair-' + str(pair) + '-' + mode)
            case.mkdir(mode=0o755)
            upstream = case / 'upstream'
            upstream.mkdir(mode=0o755)
            os.chown(upstream, 1001, 1001)
            for source in certificate_root.iterdir():
                if source.is_file():
                    shutil.copyfile(source, upstream / source.name)
                    (upstream / source.name).chmod(0o644)
            configuration = case / 'control'
            configuration.mkdir(mode=0o755)
            shutil.copyfile(certificate_root / 'ca.der', configuration / 'verification-ca.der')
            native = case / 'native'
            native.mkdir(mode=0o700)
            os.chown(native, 1001, 1001)
            config = {'binding': {'account_id': 1, 'environment_id': 'fixture', 'generation': 1,
                'endpoint': 'http://127.0.0.1:8091', 'secret': 'f' * 64},
                'proxy_url': 'http://127.0.0.1:1081', 'allowed_origin': 'https://api.anthropic.com',
                'native': {'binary_path': '/usr/local/bin/ccrb-runtime', 'work_root': '/native',
                    'memory_mib': 1536, 'max_workers': 6}}
            (configuration / 'sender.json').write_text(json.dumps(config))
            (configuration / 'sender.json').chmod(0o644)
            sender = None
            try:
                sender = client.containers.run(image, name='bench-scratchpad-perf-' + uuid.uuid4().hex[:16],
                    entrypoint=['python3', '-I', '-c', _SERVER], detach=True, network_mode='none',
                    user='1001:1001', read_only=True, cap_drop=['ALL'], security_opt=['no-new-privileges:true'],
                    mem_limit='2g', memswap_limit='2g', nano_cpus=2_000_000_000,
                    tmpfs={'/tmp': 'rw,noexec,nosuid,nodev,size=16m,mode=1777'},
                    volumes={str(Path(__file__).with_name('fixtures').resolve()): {'bind': '/fixtures', 'mode': 'ro'},
                        str(upstream): {'bind': '/fixtures-data', 'mode': 'rw'},
                        str(configuration): {'bind': '/run/v3', 'mode': 'ro'}, str(native): {'bind': '/native', 'mode': 'rw'}},
                    labels={'vibebench.product': 'v3', 'vibebench.deployment': 'scratchpad-perf-fixture'})
                measured = sender.exec_run(['python3', '-I', '-c', _MEASURE], user='1001:1001')
                if measured.exit_code:
                    (case / 'sender.log').write_bytes(sender.logs(tail=30))
                    raise ValueError('sender性能验证失败：' + measured.output.decode(errors='replace')[-2500:])
                value = json.loads(measured.output)
                counter = cli.exec_run(['cat', '/tmp/claude-1000/performance/stats.json'])
                if counter.exit_code:
                    raise ValueError('CLI写入负载未确认')
                value.update(mode=mode, pair=pair, writer=json.loads(counter.output))
                results.append(value)
                (work / 'progress.json').write_text(json.dumps({'completed_rounds': len(results), 'total_rounds': pairs * 2}))
            finally:
                stop.touch()
                deadline = time.monotonic() + 3
                while client.api.exec_inspect(writer)['Running'] and time.monotonic() < deadline:
                    time.sleep(.05)
                if sender is not None:
                    sender.remove(force=True)
    return {'pairs': pairs, 'requests_per_round': 60, 'concurrency': 3,
        'cli_write_bytes_per_second': 40 * 1024 * 1024, 'cli_fsync': True,
        'cpu_scope': 'sender容器，包括同容器的隔离上游与HTTP探针', 'rounds': results}
