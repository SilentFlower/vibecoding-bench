"""复用统一后台的 Chrome 会话验证养号阈值表单和真实 API，不使用账号凭据。"""

import base64
from pathlib import Path
from native_ui import click_text


async def verify_warmup_ui(rpc, evaluate, wait_for, session_id: str) -> None:
    """在合成账号页面验证开关、输入、保存和窄屏。

    :param rpc: 现有 CDP 命令函数
    :param evaluate: 已鉴权页面的脚本执行函数
    :param wait_for: 有界等待页面条件的函数
    :param session_id: 本次私有 Chrome 的 CDP 会话
    :return: None；不符时抛异常，截图只包含合成账号
    """
    frame = "document"
    await wait_for(f"Boolean({frame}?.querySelector('[data-warmup-config]'))")
    await evaluate(f"{frame}.querySelector('[data-warmup-config]').click()")
    await wait_for(f"!{frame}.querySelector('#warmup-modal').classList.contains('hidden')")
    assert await evaluate(f"Array.from({frame}.querySelectorAll('#warmup-form input[name^=quota_]')).every(input=>!input.checked)")
    assert await evaluate(f"{frame}.querySelector('#warmup-form').elements.enabled.disabled")
    assert await evaluate(f"{frame}.querySelector('#warmup-binding-hint').textContent.includes('此处只修改账号额度阈值')")

    await evaluate(f"(() => {{ const doc={frame}; const form=doc.querySelector('#warmup-form');"
        "for (const [window,value] of [['5h','30'],['7d','20']]) {"
        "const on=form.elements['quota_'+window+'_enabled']; on.checked=true; on.dispatchEvent(new Event('change'));"
        "const input=form.elements['warmup_quota_'+window+'_limit_percent']; input.value=value; input.dispatchEvent(new Event('input'));"
        "} })()")
    assert await evaluate(f"{frame}.querySelector('#warmup-quota-5h-hint').textContent.includes('剩余 70%')")
    assert await evaluate(f"{frame}.querySelector('#warmup-quota-7d-hint').textContent.includes('剩余 80%')")
    await evaluate(f"(() => {{ const form={frame}.querySelector('#warmup-form');"
        "form.elements.warmup_quota_5h_limit_percent.value='101'; })()")
    assert not await evaluate(f"{frame}.querySelector('#warmup-form').checkValidity()")
    await evaluate(f"{frame}.querySelector('#warmup-form').elements.warmup_quota_5h_limit_percent.value='30'")

    for width in (1280, 390):
        await rpc("Emulation.setDeviceMetricsOverride", {"width": width, "height": 900, "deviceScaleFactor": 1, "mobile": False}, session_id)
        for theme in ("dark", "light"):
            await evaluate(f"(() => {{const doc={frame}; if (doc.querySelector('.task-runtime').dataset.theme !== '{theme}') doc.querySelector('#theme-toggle').click();}})()")
            # 输入框背景有 120ms 过渡；等待真实主题按钮切换后的绘制，避免截到明暗混合帧。
            await evaluate(f"new Promise(resolve => {frame}.defaultView.setTimeout(resolve, 250))")
            bounds = await evaluate(f"(() => {{const doc={frame}; const card=doc.querySelector('#warmup-modal .modal-card').getBoundingClientRect();"
                "return {left:card.left,right:card.right,width:doc.defaultView.innerWidth};})()")
            assert bounds["left"] >= -1 and bounds["right"] <= bounds["width"] + 1
            screenshot = await rpc("Page.captureScreenshot", {"format": "png"}, session_id)
            Path(f"/tmp/v3-warmup-form-{width}-{theme}.png").write_bytes(base64.b64decode(screenshot["data"]))

    await evaluate(f"{frame}.querySelector('#warmup-form button[type=submit]').scrollIntoView({{block:'center'}})")
    assert await evaluate(f"(() => {{const doc={frame}; const button=doc.querySelector('#warmup-form button[type=submit]').getBoundingClientRect();"
        "return button.top >= 0 && button.bottom <= doc.defaultView.innerHeight;})()")

    await evaluate(f"{frame}.querySelector('#warmup-form').requestSubmit()")
    await wait_for(f"{frame}.querySelector('#warmup-modal').classList.contains('hidden')")
    accounts = await evaluate("fetch('/runtime/api/accounts').then(response=>response.json())")
    account = next(item for item in accounts if item["name"] == "warmup-ui-fixture")
    assert account["warmup_quota_5h_limit_percent"] == 30
    assert account["warmup_quota_7d_limit_percent"] == 20
    assert account["warmup_enabled"] == 0
    await evaluate(f"{frame}.querySelector('[data-warmup-config]').click()")
    await wait_for(f"!{frame}.querySelector('#warmup-modal').classList.contains('hidden')")
    assert await evaluate(f"{frame}.querySelector('#warmup-form').elements.warmup_quota_5h_limit_percent.value") == "30"
    await evaluate(f"(() => {{const form={frame}.querySelector('#warmup-form');"
        "form.elements.quota_5h_enabled.checked=false; form.elements.quota_5h_enabled.dispatchEvent(new Event('change'));"
        "form.requestSubmit();})()")
    await wait_for(f"{frame}.querySelector('#warmup-modal').classList.contains('hidden')")
    accounts = await evaluate("fetch('/runtime/api/accounts').then(response=>response.json())")
    account = next(item for item in accounts if item["name"] == "warmup-ui-fixture")
    assert account["warmup_quota_5h_limit_percent"] is None
    assert account["warmup_quota_7d_limit_percent"] == 20
    assert "admission" not in account["warmup_quota"]
    for policy in (account["quota_policy"],account["warmup_quota"]):
        assert not policy["blocked"] and policy["unknown"]==["seven_day"],policy
    await evaluate("document.querySelector('[data-account-details]').click()")
    await wait_for("document.querySelector('#modal').textContent.includes('7d 已用 ≥ 20%')")
    await evaluate("document.querySelector('#modal-close').click()")
    await evaluate("document.querySelector('.console-sidebar a[href=\"/environments\"]').click()")
    await wait_for('Boolean(document.querySelector(".environment-rich"))')
    await click_text(evaluate,'.fui-entity-card-actions button','维护')
    await wait_for('Boolean(document.querySelector(".runtime-environment-dialog"))')
    assert not await evaluate("[...document.querySelectorAll('.maintenance-option button')].find(e=>e.textContent.trim()==='校正画像').disabled")
    before=await evaluate('fetch("/runtime/api/environments").then(r=>r.json())')
    await click_text(evaluate,'.maintenance-option button','校正画像')
    await wait_for("[...document.querySelectorAll('[role=dialog]')].some(e=>e.textContent.includes('持久数据会保留'))")
    await click_text(evaluate,'.runtime-dialog-actions button','取消')
    after=await evaluate('fetch("/runtime/api/environments").then(r=>r.json())')
    assert [(e['environment_id'],e['generation'],e['fingerprint']) for e in before]==[(e['environment_id'],e['generation'],e['fingerprint']) for e in after]
    await evaluate('document.querySelector("[aria-label=关闭环境详情]").click()')
    print("通过：Pi 养号独立工程计划与账号阈值分离；画像校正确认提示、双状态、严格输入、保存重读、桌面/390px 与明暗主题正常")
