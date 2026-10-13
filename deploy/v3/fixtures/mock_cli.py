#!/usr/bin/env python3
"""仅用于隔离生命周期测试的 CLI 替身，不打入产品镜像。"""
import json
import os
import sys
import time
from pathlib import Path
from urllib.parse import urlencode

home = Path(os.environ["HOME"])
if "--version" in sys.argv:
    print("9.9.9 (Synthetic lifecycle fixture)")
elif sys.argv[1:] == ["auth", "status"]:
    print(json.dumps({"loggedIn": (home / ".claude" / ".credentials.json").exists(), "authMethod": "oauth"}))
elif sys.argv[1:] == ["auth", "login"]:
    control_home = home.parents[1] if home.parent.name == ".v3-login" else home
    control_file = control_home / ".synthetic-login.json"
    control = json.loads(control_file.read_text()) if control_file.exists() else {}
    print("合成 CLI 登录会话", flush=True)
    if control.get("wait_for_code"):
        endpoint = "https://claude.com/cai/oauth/authorize" if control.get("new_endpoint") else "https://claude.ai/oauth/authorize"
        link = endpoint + "?" + urlencode({"client_id": "synthetic-client", "response_type": "code",
            "redirect_uri": "https://platform.claude.com/oauth/code/callback", "scope": "user:profile user:inference",
            "code_challenge": "c" * 43, "code_challenge_method": "S256", "state": "s" * 43})
        print(link, flush=True)
        print("请输入合成授权码：", flush=True)
        while True:
            code = sys.stdin.readline().strip()
            if code == "synthetic-exit":
                sys.exit(0)
            if code == "synthetic-code":
                break
            print("合成授权码不匹配", flush=True)
    (home / ".claude").mkdir(exist_ok=True)
    (home / ".claude" / ".credentials.json").write_text(json.dumps({"claudeAiOauth": {"accessToken": control.get("access_token", "synthetic"), "refreshToken": control.get("refresh_token", "synthetic-rt"),
        "expiresAt": int(time.time() * 1000) + 3600000}}))
    top = json.loads((home / ".claude.json").read_text()) if (home / ".claude.json").exists() else {}
    top["oauthAccount"] = {"accountUuid": control.get("account_uuid", "synthetic-uuid"),
        "organizationUuid": control.get("organization_uuid", "synthetic-org"), "emailAddress": control.get("email", "synthetic@example.invalid")}
    (home / ".claude.json").write_text(json.dumps(top))
    print("合成登录完成", flush=True)
    while True:
        time.sleep(1)
else:
    (Path.cwd() / ".synthetic-invocation.json").write_text(json.dumps({"args": sys.argv[1:], "cwd": str(Path.cwd()), "home": str(home)}))
    print("Synthetic task pane", flush=True)
    while True:
        time.sleep(1)
