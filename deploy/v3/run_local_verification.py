#!/usr/bin/env python3
"""创建专用内部网络和测试容器，结束只删除本次随机标签资源。"""
import argparse
import asyncio
import ipaddress
import json
import os
import select
import shutil
import socket
import socketserver
import subprocess
import tempfile
import threading
import time
import uuid
from pathlib import Path
from contextlib import contextmanager

import docker
from docker.types import IPAMConfig, IPAMPool


@contextmanager
def scenario_loopback_forward(address: str):
    """仅在回环转发到本次内部验证容器，保留SSE及原Bearer鉴权。

    :param address: 本次随机内部网络中的验证服务IP。
    :return: 有界生命周期的本机访问地址。
    """
    class Handler(socketserver.BaseRequestHandler):
        """转发当前连接，不解析或记录认证内容。"""

        def handle(self) -> None:
            """双向复制当前测试TCP连接。@return None。"""
            with socket.create_connection((address,8000),timeout=5) as remote:
                remote.settimeout(None)
                while True:
                    readable,_,_=select.select([self.request,remote],[],[],30)
                    if not readable:
                        continue
                    for source in readable:
                        content=source.recv(65536)
                        if not content:
                            return
                        (remote if source is self.request else self.request).sendall(content)

    class Server(socketserver.ThreadingTCPServer):
        """允许浏览器并发读取和长连接，结束后不保留后台线程。"""
        daemon_threads=True

    with Server(('127.0.0.1',0),Handler) as server:
        thread=threading.Thread(target=server.serve_forever,daemon=True)
        thread.start()
        try:
            yield 'http://127.0.0.1:'+str(server.server_address[1])
        finally:
            server.shutdown()
            thread.join(timeout=5)


def main() -> None:
    """运行只含合成数据的 Docker 验证。

    :return: None；失败时非零退出
    """
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--legacy-control-image")
    parser.add_argument("--legacy-account-image")
    parser.add_argument("--project-iterations-only", action="store_true")
    parser.add_argument("--project-scheduling-only", action="store_true")
    parser.add_argument('--project-scenarios-only', action='store_true')
    parser.add_argument('--scenario-capacity', type=int, choices=(1,2), default=2)
    parser.add_argument('--scenario-browser',action='store_true')
    parser.add_argument('--scenario-failures',action='store_true')
    parser.add_argument("--project-catalog-only", action="store_true")
    parser.add_argument("--evidence-dir", type=Path)
    parser.add_argument("--run-windows-only", action="store_true")
    parser.add_argument("--followups-only", action="store_true")
    parser.add_argument("--timed-followups-only", action="store_true")
    parser.add_argument("--quota-completion-only", "--quota-hard-stop-only", dest="quota_completion_only", action="store_true")
    args = parser.parse_args()
    if (args.scenario_browser or args.scenario_failures) and not args.project_scenarios_only:
        parser.error('场景浏览器及恢复验证只能用于新场景独立验证')
    if bool(args.legacy_control_image) != bool(args.legacy_account_image):
        parser.error("旧布局验证需要同时提供旧 control/account 镜像")
    if args.project_catalog_only and any((args.project_iterations_only,args.project_scheduling_only,
            args.run_windows_only,args.followups_only,args.timed_followups_only,args.quota_completion_only)):
        parser.error("百项目规模场景须单独执行")
    if args.evidence_dir:
        args.evidence_dir.mkdir(parents=True,exist_ok=False,mode=0o700)
        args.evidence_dir = args.evidence_dir.resolve()
    manifest = json.loads(args.manifest.read_text())
    if args.evidence_dir:
        (args.evidence_dir/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    repository = Path(__file__).resolve().parents[2]
    client = docker.from_env()
    deployment = "verify-" + uuid.uuid4().hex[:12]
    labels = {"vibebench.product": "v3", "vibebench.deployment": deployment}
    used = [ipaddress.ip_network(item['Subnet']) for existing in client.networks.list()
        for item in existing.attrs.get('IPAM', {}).get('Config') or [] if item.get('Subnet')]
    routes = json.loads(subprocess.check_output(['ip', '-j', 'route', 'show']))
    used.extend(ipaddress.ip_network(item['dst']) for item in routes if item.get('dst') not in (None, 'default'))
    subnets = [str(candidate) for index in range(200, 250)
        for candidate in [ipaddress.ip_network(f'10.232.{index}.0/24')]
        if not any(candidate.overlaps(item) for item in used if item.version == 4)]
    for subnet in subnets:
        try:
            network = client.networks.create("vibebench-v3-" + deployment, internal=True, labels=labels,
                ipam=IPAMConfig(pool_configs=[IPAMPool(subnet=subnet)]))
            break
        except docker.errors.APIError as error:
            # 并行验证可能在扫描后认领同一子网，只对这一原子分配冲突换候选。
            if 'Pool overlaps' not in str(error):
                raise
    else:
        raise RuntimeError('没有可用的独立验证子网')
    try:
        with tempfile.TemporaryDirectory(prefix="vibebench-v3-verify-",dir=args.evidence_dir) as temporary:
            root = Path(temporary)
            subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "1",
                "-subj", "/CN=api.anthropic.com", "-addext", "subjectAltName=DNS:api.anthropic.com",
                "-keyout", str(root / "native-usage.key"), "-out", str(root / "native-usage.crt")],
                check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            fixtures = repository / "deploy" / "v3" / "fixtures"
            mock = client.containers.run(manifest["images"]["control"]["reference"], ["/fixtures/mock_network.py"], entrypoint="python", detach=True,
                network=network.name, labels={**labels, "vibebench.role": "verification"},
                volumes={str(fixtures): {"bind": "/fixtures", "mode": "ro"}, str(root): {"bind": "/fixtures-data", "mode": "rw"}})
            mock.reload()
            proxy = mock.attrs["NetworkSettings"]["Networks"][network.name]["IPAddress"]
            service_token=uuid.uuid4().hex+uuid.uuid4().hex
            runner = client.containers.run(manifest["images"]["control"]["reference"], ["/source/deploy/v3/verify_local.py", "--proxy-ip", proxy], entrypoint="python", detach=True,
                network=network.name, labels={**labels, "vibebench.role": "orchestrator"},
                environment={"PYTHONPATH": "/source/orchestrator", "V3_DEPLOYMENT_ID": deployment, "V3_RELEASE": manifest["release"],
                    "V3_ACCOUNT_IMAGE": manifest["images"]["account"]["reference"], "V3_NETWORK": network.name, "VERIFY_HOST_ROOT": str(root), "V3_WORKER_SCRIPT": "/source/images/worker/entrypoint.sh",
                    "V3_ACCOUNT_MEMORY": "1536m", "V3_ACCOUNT_SWAP": "2048m",
                    "VERIFY_LEGACY_CONTROL_IMAGE": args.legacy_control_image or "",
                    "VERIFY_LEGACY_ACCOUNT_IMAGE": args.legacy_account_image or "",
                    "VERIFY_SOURCE_ROOT": str(repository),
                    "VERIFY_FOLLOWUPS_ONLY": "1" if args.followups_only or args.timed_followups_only else "0",
                    "VERIFY_TIMED_FOLLOWUPS_ONLY": "1" if args.timed_followups_only else "0",
                    "VERIFY_QUOTA_COMPLETION_ONLY": "1" if args.quota_completion_only else "0",
                    "VERIFY_RUN_WINDOWS_ONLY": "1" if args.run_windows_only else "0",
                    "VERIFY_PROJECT_ITERATIONS_ONLY": "1" if args.project_iterations_only else "0",
                    "VERIFY_PROJECT_SCHEDULING_ONLY": "1" if args.project_scheduling_only else "0",
                    'VERIFY_PROJECT_SCENARIOS_ONLY':'1' if args.project_scenarios_only else '0',
                    'VERIFY_SCENARIO_BROWSER':'1' if args.scenario_browser else '0',
                    'VERIFY_SCENARIO_FAILURES':'1' if args.scenario_failures else '0',
                    'V3_INTERNAL_TOKEN':service_token,'WEBUI_DIR':'/source/webui',
                    'PER_ACCOUNT_CONCURRENCY':str(args.scenario_capacity) if args.project_scenarios_only else os.environ.get('PER_ACCOUNT_CONCURRENCY','2'),
                    "VERIFY_PROJECT_CATALOG_ONLY": "1" if args.project_catalog_only else "0",
                    "VERIFY_PROJECT_SCHEDULING_TASKS_ONLY": os.environ.get("VERIFY_PROJECT_SCHEDULING_TASKS_ONLY", "0")},
                volumes={str(repository): {"bind": "/source", "mode": "ro"}, str(fixtures): {"bind": "/fixtures", "mode": "ro"},
                    str(root): {"bind": "/verify", "mode": "rw"}, "/var/run/docker.sock": {"bind": "/var/run/docker.sock", "mode": "rw"}})
            # 完整补充矩阵包含逐次CLI启动和原生忙碌消费，外层等待不能先于场景自身截止时间结束。
            if args.evidence_dir:
                (args.evidence_dir/'runtime.json').write_text(json.dumps({'deployment':deployment,
                    'runner_id':runner.id,'network':network.name,'root':str(root),'release':manifest['release']},indent=2)+'\n')
            try:
                if args.scenario_browser:
                    from verify_scenario_browser import verify_scenario_browser
                    ready=root/'scenario-browser-ready.json'
                    deadline=time.monotonic()+90
                    while not ready.exists():
                        runner.reload()
                        if runner.status!='running' or time.monotonic()>deadline:
                            raise RuntimeError('新场景浏览器服务未能就绪')
                        time.sleep(0.2)
                    runner.reload()
                    service_address=runner.attrs['NetworkSettings']['Networks'][network.name]['IPAddress']
                    try:
                        with scenario_loopback_forward(service_address) as browser_base:
                            browser=asyncio.run(verify_scenario_browser(browser_base,service_token,
                                (args.evidence_dir/'browser') if args.evidence_dir else root/'scenario-browser-evidence',
                                expected_capacity=args.scenario_capacity,timeout_sec=900,
                                catalog_fault_request=root/'scenario-catalog-fault.json'))
                    except BaseException:
                        (root/'scenario-browser-result.json').write_text(json.dumps({'status':'failed'}))
                        raise
                    (root/'scenario-browser-result.json').write_text(json.dumps(browser,ensure_ascii=False))
                result = runner.wait(timeout=20000 if args.project_catalog_only else 1200)
            except BaseException:
                # 中断时先停止写入者，再让临时目录退出，避免清理期间又产生文件。
                for instance in client.containers.list(all=True,filters={"label":["vibebench.product=v3","vibebench.deployment="+deployment]}):
                    try:
                        instance.stop(timeout=2)
                    except docker.errors.NotFound:
                        pass
                raise
            finally:
                if args.evidence_dir:
                    (args.evidence_dir/'runner.log').write_bytes(runner.logs())
                    for instance in client.containers.list(all=True,filters={"label":["vibebench.product=v3","vibebench.deployment="+deployment]}):
                        role = instance.labels.get('vibebench.role','unknown')
                        (args.evidence_dir/(role+'-'+instance.short_id+'.log')).write_bytes(instance.logs(tail=150))
                    for path in root.glob('catalog-*'):
                        if path.is_file() and not path.is_symlink():
                            shutil.copy2(path,args.evidence_dir/path.name)
                    for path in root.glob('scenario-*'):
                        if path.is_file() and not path.is_symlink():
                            shutil.copy2(path,args.evidence_dir/path.name)
            print(runner.logs().decode())
            if result["StatusCode"] != 0:
                for instance in client.containers.list(all=True, filters={"label": ["vibebench.deployment=" + deployment, "vibebench.role=account-network"]}):
                    print(instance.logs(tail=25).decode())
                raise SystemExit(result["StatusCode"])
    finally:
        for instance in client.containers.list(all=True, filters={"label": ["vibebench.product=v3", "vibebench.deployment=" + deployment]}):
            instance.remove(force=True)
        network.remove()


if __name__ == "__main__":
    main()
