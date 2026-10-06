"""同步被动额度纯函数到独立 sidecar 构建上下文，避免两套判定漂移。"""

from pathlib import Path


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1]
    source = root / "orchestrator" / "quota_protocol.py"
    target = root / "images" / "sidecar" / "quota_protocol.py"
    target.write_bytes(source.read_bytes())
