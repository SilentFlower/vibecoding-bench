#!/usr/bin/env python3
"""在无外网 Docker 网络中验证实际 Recorder 的 HTTPS 收尾与单次请求，不使用真实账号。"""

import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import uuid

import docker
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "orchestrator"))
from quota_protocol import warmup_quota_decision


UPSTREAM_SCRIPT = '''"""仅在隔离网络内返回合成 HTTPS/SSE 响应。"""
import json
import ssl
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

class Handler(BaseHTTPRequestHandler):
    """提供带有限延迟的合成流；参数为 HTTP 请求，返回响应字节。"""
    protocol_version = "HTTP/1.1"

    def do_POST(self):
        """记录合成场景名并发送完整 SSE，返回 None。"""
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0"))))
        mode = body.get("mode")
        with Path("/lab/requests.jsonl").open("a") as record:
            record.write(json.dumps({"mode": mode}) + "\\n")
        parts = [("data: " + json.dumps({"sequence": index, "payload": "x" * 8192}) + "\\n\\n").encode() for index in range(40)]
        parts.append(b"data: [DONE]\\n\\n")
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Content-Length", str(sum(map(len, parts))))
        if mode != "unknown":
            self.send_header("anthropic-ratelimit-unified-5h-utilization", "0.3" if mode == "hit" else "0.2")
            self.send_header("anthropic-ratelimit-unified-5h-status", "allowed")
            self.send_header("anthropic-ratelimit-unified-5h-reset", str(time.time() + 600))
        self.end_headers()
        for part in parts:
            self.wfile.write(part)
            self.wfile.flush()
            time.sleep(0.05)

    def log_message(self, format, *args):
        """关闭请求默认日志，返回 None。"""
        pass

server = ThreadingHTTPServer(("0.0.0.0", 443), Handler)
context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
context.load_cert_chain("/lab/upstream.crt", "/lab/upstream.key")
server.socket = context.wrap_socket(server.socket, server_side=True)
server.serve_forever()
'''

CLIENT_SCRIPT = '''import hashlib,json,os,sys
import requests
client=requests.Session()
client.trust_env=False
with client.post("https://api.anthropic.com/v1/messages",json={"mode":sys.argv[2]},
        headers={"Authorization":"Bearer "+os.environ["SYNTHETIC_TOKEN"]},
        proxies={"https":sys.argv[1]},verify="/lab/mitm/mitmproxy-ca-cert.pem",timeout=15,stream=True) as response:
    body=b"".join(response.iter_content(16384))
    print(json.dumps({"status":response.status_code,"size":len(body),
        "complete":body.endswith(b"data: [DONE]\\n\\n"),"sha256":hashlib.sha256(body).hexdigest()}))
client.close()
'''


def wait_for(condition, description: str, timeout: float = 12) -> None:
    """有界等待本地条件，参数为判断函数/说明/秒数，超时抛异常，返回 None。"""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if condition():
            return
        time.sleep(0.05)
    raise AssertionError(description)


def main() -> None:
    """读取指定镜像清单并运行合成验证，返回 None；失败保留非敏感日志。"""
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text())
    client = docker.from_env()
    deployment = "warmup-test-" + uuid.uuid4().hex[:10]
    labels = {"vibebench.product": "v3", "vibebench.deployment": deployment, "vibebench.role": "verification"}
    baseline = {}
    for item in client.containers.list():
        state = item.attrs["State"]
        # Docker 默认列表包含 restarting；它本来就在变化，不能当作稳定运行基线。
        if state["Restarting"]:
            print(f"基线说明：{item.name} 启动前已处于自动重启，不校验其启动时间稳定性")
            continue
        baseline[item.id] = {"name": item.name, "started": state["StartedAt"]}
    network = client.networks.create("vibebench-v3-" + deployment, internal=True, labels=labels)
    instances = []
    try:
        with tempfile.TemporaryDirectory(prefix="v3-warmup-https-") as temporary:
            root = Path(temporary)
            (root / "upstream.py").write_text(UPSTREAM_SCRIPT)
            subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "1",
                "-keyout", str(root / "upstream.key"), "-out", str(root / "upstream.crt"),
                "-subj", "/CN=api.anthropic.com", "-addext", "subjectAltName=DNS:api.anthropic.com",
                "-addext", "basicConstraints=critical,CA:TRUE"], check=True, capture_output=True)
            (root / "upstream.key").chmod(0o600)
            upstream = client.containers.run(manifest["images"]["control"]["reference"], ["/lab/upstream.py"],
                entrypoint="python", detach=True, network=network.name,
                networking_config={network.name: client.api.create_endpoint_config(aliases=["api.anthropic.com"])},
                labels=labels, volumes={str(root): {"bind": "/lab", "mode": "rw"}})
            instances.append(upstream)
            driver = client.containers.run(manifest["images"]["control"]["reference"],
                ["-c", "import time; time.sleep(600)"], entrypoint="python", detach=True,
                network=network.name, labels=labels, volumes={str(root): {"bind": "/lab", "mode": "ro"}})
            instances.append(driver)
            token = "synthetic-warmup-access-token"
            expected_body = b"".join(("data: " + json.dumps({"sequence": index, "payload": "x" * 8192}) + "\n\n").encode()
                                     for index in range(40)) + b"data: [DONE]\n\n"
            expected_sha = hashlib.sha256(expected_body).hexdigest()
            state_file = root / "state.json"
            signal = root / "pause.json"
            limits = {"five_hour": 30, "seven_day": None}

            def policy(windows, source="run:fixture:0"):
                """发布合成额度与匹配许可；参数为窗口/来源，返回 None。"""
                now = time.time()
                decision = warmup_quota_decision({"windows": windows}, limits, now)
                admission = {"identity": "fixture-identity", "source": source,
                    **{key: decision[key] for key in ("policy_key", "window_key")}}
                value = {"identity": "fixture-identity", "token_hashes": [hashlib.sha256(token.encode()).hexdigest()],
                         "windows": windows, "warmup_quota": {**decision, "admission": admission}}
                temporary_path = state_file.with_suffix(".tmp")
                temporary_path.write_text(json.dumps(value))
                temporary_path.replace(state_file)

            def start_proxy(warmup=True):
                """启动真实镜像内的 Recorder；参数为作用域开关，返回容器与代理地址。"""
                instance = client.containers.run(manifest["images"]["account"]["reference"],
                    ["--mode", "regular", "--listen-host", "0.0.0.0", "--listen-port", "8080", "-s", "/sidecar/recorder.py",
                     "--set", "ssl_verify_upstream_trusted_ca=/lab/upstream.crt"],
                    entrypoint="/opt/mitm/bin/mitmdump", detach=True, network=network.name, labels=labels,
                    environment={"HOME": "/root", "QUOTA_SOURCE": "run:fixture:0", "QUOTA_IDENTITY": "fixture-identity",
                        "QUOTA_WARMUP": "1" if warmup else "0", "QUOTA_STATE_FILE": "/lab/state.json",
                        "QUOTA_SIGNAL_FILE": "/lab/pause.json", "QUOTA_OBSERVATIONS_FILE": "/lab/observations.jsonl",
                        "STATS_FILE": "/lab/stats.jsonl"},
                    volumes={str(root): {"bind": "/lab", "mode": "rw"},
                             str(root / "mitm"): {"bind": "/root/.mitmproxy", "mode": "rw"}})
                instances.append(instance)
                instance.reload()
                address = "http://" + instance.attrs["NetworkSettings"]["Networks"][network.name]["IPAddress"] + ":8080"
                wait_for(lambda: (root / "mitm/mitmproxy-ca-cert.pem").exists(), "MITM CA 未就绪")
                def listening():
                    """以真实 TCP 确认启动，不依赖缓冲日志字符串。"""
                    instance.reload()
                    if not instance.attrs["State"]["Running"]:
                        raise AssertionError("MITM 提前退出：" + instance.logs(tail=10).decode())
                    result = driver.exec_run(["python", "-c", "import socket,sys; socket.create_connection((sys.argv[1],8080),timeout=0.2).close()",
                                              instance.attrs["NetworkSettings"]["Networks"][network.name]["IPAddress"]])
                    return result.exit_code == 0
                wait_for(listening, "MITM 监听未就绪")
                return instance, address

            def request(address, mode):
                """在内部网络调用合成 HTTPS，参数为代理地址/场景，返回状态与正文摘要。"""
                result = driver.exec_run(["python", "-c", CLIENT_SCRIPT, address, mode], environment={"SYNTHETIC_TOKEN": token})
                if result.exit_code != 0:
                    raise AssertionError("合成客户端失败：" + result.output.decode()[-1500:])
                summary = json.loads(result.output)
                return summary["status"], summary

            def records():
                """读取本地上游实际收到的场景名，返回列表。"""
                path = root / "requests.jsonl"
                return [json.loads(line)["mode"] for line in path.read_text().splitlines()] if path.exists() else []

            policy({"five_hour": {"utilization": 20, "reset_at": time.time() + 600, "observed_at": time.time()}})
            proxy, address = start_proxy()
            with ThreadPoolExecutor(max_workers=2) as pool:
                first = pool.submit(request, address, "hit")
                wait_for(lambda: signal.with_name("warmup-draining.json").exists(), "命中后没有进入收尾状态")
                assert not signal.exists() and not first.done()
                assert request(address, "late")[0] == 429
                status, body = first.result(timeout=15)
                assert status == 200 and body["complete"] and body["sha256"] == expected_sha and body["size"] == len(expected_body)
                wait_for(signal.exists, "成功流结束后没有暂停")
                assert json.loads(signal.read_text())["warmup_wait"] is True
                assert records() == ["hit"]
            proxy.stop(timeout=5)
            for path in (signal, root / "warmup-sample.json", root / "warmup-draining.json"):
                path.unlink(missing_ok=True)
            policy({})
            proxy, address = start_proxy()
            with ThreadPoolExecutor(max_workers=2) as pool:
                first = pool.submit(request, address, "unknown")
                wait_for(lambda: "unknown" in records(), "未知机会没有真实请求")
                wait_for(lambda: signal.with_name("warmup-draining.json").exists(), "未知请求未保留收尾")
                assert request(address, "duplicate")[0] == 429
                status, body = first.result(timeout=15)
                assert status == 200 and body["complete"] and body["sha256"] == expected_sha
                wait_for(signal.exists, "未知请求结束后没有暂停")
            proxy.restart(timeout=5)
            # Docker restart 返回不等于 Python 已监听，使用本地连接条件再确认。
            def ready():
                """从同一内部网络检查代理真实监听，返回布尔值。"""
                result = driver.exec_run(["python", "-c", "import socket,sys; socket.create_connection((sys.argv[1],8080),timeout=0.2).close()",
                                          proxy.attrs["NetworkSettings"]["Networks"][network.name]["IPAddress"]])
                return result.exit_code == 0
            proxy.reload()
            address = "http://" + proxy.attrs["NetworkSettings"]["Networks"][network.name]["IPAddress"] + ":8080"
            wait_for(ready, "重启代理未监听")
            assert request(address, "after-restart")[0] == 429
            assert records() == ["hit", "unknown"]
            proxy.stop(timeout=5)
            signal.unlink(missing_ok=True)
            normal, normal_address = start_proxy(warmup=False)
            assert request(normal_address, "normal")[0] == 200
            assert not signal.exists()
            assert records() == ["hit", "unknown", "normal"]
            print("通过：真实镜像 Recorder、受信任本地 HTTPS/SSE、完整响应收尾、后续拒绝、未知仅一次、重启不重复、普通作用域放行")
    except Exception:
        for instance in instances:
            instance.reload()
            print("合成服务诊断：", instance.attrs["State"]["Status"], instance.logs(tail=10).decode())
        raise
    finally:
        for instance in reversed(instances):
            instance.remove(force=True)
        network.remove()
        for container_id, previous in baseline.items():
            current = client.containers.get(container_id)
            current.reload()
            state = current.attrs["State"]
            assert state["Running"] and state["StartedAt"] == previous["started"], f"基线容器状态变化：{previous['name']}"
        client.close()


if __name__ == "__main__":
    os.umask(0o077)
    main()
