#!/usr/bin/env python3
"""创建专用内部网络和测试容器，结束只删除本次随机标签资源。"""
import argparse
import json
import os
import subprocess
import tempfile
import uuid
from pathlib import Path

import docker


def main() -> None:
    """运行只含合成数据的 Docker 验证。

    :return: None；失败时非零退出
    """
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text())
    repository = Path(__file__).resolve().parents[2]
    client = docker.from_env()
    deployment = "verify-" + uuid.uuid4().hex[:12]
    labels = {"vibebench.product": "v3", "vibebench.deployment": deployment}
    network = client.networks.create("vibebench-v3-" + deployment, internal=True, labels=labels)
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
                network=network.name, labels={**labels, "vibebench.role": "verification"},
                environment={"PYTHONPATH": "/source/orchestrator", "V3_DEPLOYMENT_ID": deployment, "V3_RELEASE": manifest["release"],
                    "V3_ACCOUNT_IMAGE": manifest["images"]["account"]["reference"], "V3_NETWORK": network.name, "VERIFY_HOST_ROOT": str(root), "V3_WORKER_SCRIPT": "/source/images/worker/entrypoint.sh",
                    "V3_ACCOUNT_MEMORY": "1536m", "V3_ACCOUNT_SWAP": "2048m"},
                volumes={str(repository): {"bind": "/source", "mode": "ro"}, str(fixtures): {"bind": "/fixtures", "mode": "ro"},
                    str(root): {"bind": "/verify", "mode": "rw"}, "/var/run/docker.sock": {"bind": "/var/run/docker.sock", "mode": "rw"}})
            result = runner.wait(timeout=240)
            print(runner.logs().decode())
            if result["StatusCode"] != 0:
                for instance in client.containers.list(all=True, filters={"label": ["vibebench.deployment=" + deployment, "vibebench.role=account"]}):
                    print(instance.logs(tail=25).decode())
                raise SystemExit(result["StatusCode"])
    finally:
        for instance in client.containers.list(all=True, filters={"label": ["vibebench.product=v3", "vibebench.deployment=" + deployment]}):
            instance.remove(force=True)
        network.remove()


if __name__ == "__main__":
    main()
