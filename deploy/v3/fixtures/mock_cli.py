#!/usr/bin/env python3
"""仅用于隔离生命周期测试的 CLI 替身，不打入产品镜像。"""
import json
import os
import sys
import time
from pathlib import Path

home = Path(os.environ["HOME"])
if "--version" in sys.argv:
    print("9.9.9 (Synthetic lifecycle fixture)")
elif sys.argv[1:] == ["auth", "status"]:
    print(json.dumps({"loggedIn": (home / ".claude" / ".credentials.json").exists()}))
elif sys.argv[1:] == ["auth", "login"]:
    print("Synthetic login pane", flush=True)
    (home / ".claude").mkdir(exist_ok=True)
    (home / ".claude" / ".credentials.json").write_text(json.dumps({"claudeAiOauth": {"accessToken": "synthetic", "refreshToken": "synthetic-rt",
        "expiresAt": int(time.time() * 1000) + 3600000}}))
    (home / ".claude.json").write_text(json.dumps({"oauthAccount": {"accountUuid": "synthetic-uuid"}}))
    while True:
        time.sleep(1)
else:
    (Path.cwd() / ".synthetic-invocation.json").write_text(json.dumps({"args": sys.argv[1:], "cwd": str(Path.cwd()), "home": str(home)}))
    print("Synthetic task pane", flush=True)
    while True:
        time.sleep(1)
