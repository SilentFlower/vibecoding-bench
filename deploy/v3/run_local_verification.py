#!/usr/bin/env python3
"""创建专用内部网络和测试容器，结束只删除本次随机标签资源。"""
import argparse
import ipaddress
import json
import os
import subprocess
import tempfile
import uuid
from pathlib import Path

import docker
from docker.types import IPAMConfig, IPAMPool


def main() -> None:
    """运行只含合成数据的 Docker 验证。

    :return: None；失败时非零退出
    """
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--legacy-control-image")
    parser.add_argument("--legacy-account-image")
    parser.add_argument("--followups-only", action="store_true")
    parser.add_argument("--timed-followups-only", action="store_true")
    parser.add_argument("--quota-hard-stop-only", action="store_true")
    args = parser.parse_args()
    if bool(args.legacy_control_image) != bool(args.legacy_account_image):
        parser.error("旧布局验证需要同时提供旧 control/account 镜像")
    manifest = json.loads(args.manifest.read_text())
    repository = Path(__file__).resolve().parents[2]
    client = docker.from_env()
    deployment = "verify-" + uuid.uuid4().hex[:12]
    labels = {"vibebench.product": "v3", "vibebench.deployment": deployment}
    used = [ipaddress.ip_network(item['Subnet']) for existing in client.networks.list()
        for item in existing.attrs.get('IPAM', {}).get('Config') or [] if item.get('Subnet')]
    routes = json.loads(subprocess.check_output(['ip', '-j', 'route', 'show']))
    used.extend(ipaddress.ip_network(item['dst']) for item in routes if item.get('dst') not in (None, 'default'))
    subnet = next(str(candidate) for index in range(200, 250)
        for candidate in [ipaddress.ip_network(f'10.232.{index}.0/24')]
        if not any(candidate.overlaps(item) for item in used if item.version == 4))
    network = client.networks.create("vibebench-v3-" + deployment, internal=True, labels=labels,
        ipam=IPAMConfig(pool_configs=[IPAMPool(subnet=subnet)]))
    try:
        with tempfile.TemporaryDirectory(prefix="vibebench-v3-verify-") as temporary:
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
                    "VERIFY_QUOTA_HARD_STOP_ONLY": "1" if args.quota_hard_stop_only else "0"},
                volumes={str(repository): {"bind": "/source", "mode": "ro"}, str(fixtures): {"bind": "/fixtures", "mode": "ro"},
                    str(root): {"bind": "/verify", "mode": "rw"}, "/var/run/docker.sock": {"bind": "/var/run/docker.sock", "mode": "rw"}})
            # 完整补充矩阵包含逐次CLI启动和原生忙碌消费，外层等待不能先于场景自身截止时间结束。
            result = runner.wait(timeout=1200)
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
