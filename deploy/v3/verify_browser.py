"""使用独立 Chrome 配置验证统一后台实际退出，不读取用户浏览器资料。"""
import asyncio
import json
import os
import shutil
import signal
import socket
import tempfile
import urllib.request

import requests
from websockets.asyncio.client import connect


async def verify_visible_logout(base: str, password: str, exercise=None) -> None:
    """从登录页操作到退出按钮，验证 Cookie 撤销和旧 Cookie 重放失败。

    :param base: 本地合成部署地址
    :param password: 仅用于本次合成部署的管理密码，不写入进程参数或输出
    :param exercise: 可选的已登录页面场景，复用本次 CDP 会话而不重复启动浏览器
    :return: None；失败抛出异常，最终收口本次 Chrome 进程组
    """
    chrome = shutil.which("google-chrome") or shutil.which("chromium")
    if not chrome:
        raise RuntimeError("浏览器验证需要本地 Chrome 或 Chromium")
    with tempfile.TemporaryDirectory(prefix="v3-browser-") as profile:
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            port = listener.getsockname()[1]
        process = await asyncio.create_subprocess_exec(chrome, "--headless=new", "--no-sandbox", "--disable-dev-shm-usage",
            "--disable-background-networking", "--no-first-run", "--proxy-server=http://127.0.0.1:9",
            "--proxy-bypass-list=127.0.0.1;localhost", f"--user-data-dir={profile}", f"--remote-debugging-port={port}",
            "about:blank", start_new_session=True, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
        try:
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            for attempt in range(50):
                try:
                    with opener.open(f"http://127.0.0.1:{port}/json/version", timeout=1) as response:
                        version = json.load(response)
                    break
                except OSError:
                    await asyncio.sleep(0.1)
            else:
                raise RuntimeError("本地浏览器启动失败")
            async with connect(version["webSocketDebuggerUrl"], proxy=None) as channel:
                command_id = 0

                async def rpc(method, parameters=None, session=None):
                    """顺序调用已核对的 CDP 命令，忽略无关事件，不输出参数。"""
                    nonlocal command_id
                    command_id += 1
                    payload = {"id": command_id, "method": method, "params": parameters or {}}
                    if session:
                        payload["sessionId"] = session
                    await channel.send(json.dumps(payload))
                    async with asyncio.timeout(10):
                        while True:
                            reply = json.loads(await channel.recv())
                            if reply.get("id") == command_id:
                                if "error" in reply:
                                    raise RuntimeError("浏览器命令失败：" + method)
                                return reply.get("result", {})

                target = await rpc("Target.createTarget", {"url": "about:blank"})
                attached = await rpc("Target.attachToTarget", {"targetId": target["targetId"], "flatten": True})
                session_id = attached["sessionId"]
                await rpc("Page.enable", session=session_id)

                async def evaluate(expression):
                    """执行页面操作并只返回所需值；脚本异常不回显认证信息。"""
                    reply = await rpc("Runtime.evaluate", {"expression": expression, "awaitPromise": True, "returnByValue": True}, session_id)
                    if "exceptionDetails" in reply:
                        raise RuntimeError("浏览器页面脚本执行失败")
                    return reply["result"].get("value")

                async def wait_for(expression):
                    """在有界时间内等待页面条件，不把未完成页面当作通过。"""
                    async with asyncio.timeout(15):
                        while not await evaluate(expression):
                            await asyncio.sleep(0.1)

                await rpc("Page.navigate", {"url": base + "/login"}, session_id)
                await wait_for("Boolean(document.querySelector('input[type=password]'))")
                await evaluate("(() => {const input=document.querySelector('input[type=password]');"
                    "Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(input," + json.dumps(password) + ");"
                    "input.dispatchEvent(new Event('input',{bubbles:true}));})()")
                # Input 使用 passive useVModel，需先等组件的异步状态同步，再模拟提交。
                await evaluate("new Promise(resolve=>requestAnimationFrame(()=>resolve()))")
                await evaluate("document.querySelector('form').requestSubmit()")
                await wait_for("Boolean(Array.from(document.querySelectorAll('a')).find(a=>a.textContent.trim()==='环境与任务'))")
                await evaluate("Array.from(document.querySelectorAll('a')).find(a=>a.textContent.trim()==='环境与任务').click()")
                await wait_for("Boolean(document.querySelector('iframe'))")
                assert await evaluate("fetch('/runtime/api/environments').then(response=>response.status)") == 200
                if exercise is not None:
                    await exercise(rpc, evaluate, wait_for, session_id)
                cookies = await rpc("Network.getCookies", {"urls": [base + "/runtime/"]}, session_id)
                old = next(cookie for cookie in cookies["cookies"] if cookie["name"] == "vb_v3_session")
                await evaluate("Array.from(document.querySelectorAll('button')).find(button=>button.textContent.trim()==='退出').click()")
                await wait_for("location.pathname==='/login'")
                assert await evaluate("fetch('/runtime/api/environments').then(response=>response.status)") == 401
                client = requests.Session()
                client.trust_env = False
                try:
                    assert client.get(base + "/runtime/api/environments", headers={"Cookie": old["name"] + "=" + old["value"]}, timeout=5).status_code == 401
                finally:
                    client.close()
                print("通过：真实页面登录、环境管理与退出；旧 v3 Cookie 无法重放")
        finally:
            if process.returncode is None:
                try:
                    os.killpg(process.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
                try:
                    await asyncio.wait_for(process.wait(), timeout=5)
                except TimeoutError:
                    os.killpg(process.pid, signal.SIGKILL)
                    await process.wait()
