"""隔离部署浏览器场景共用的原生页面操作。"""
import json


async def click_text(evaluate, selector: str, text: str) -> None:
    """点击指定区域的可见按钮。@param evaluate CDP求值器。@param selector 区域。@param text 文案。@return 无。"""
    await evaluate(f'''(() => {{const button=[...document.querySelectorAll({json.dumps(selector)})]
        .find(item=>item.getClientRects().length&&item.textContent.trim()==={json.dumps(text)});
        if(!button)throw new Error('未找到可见操作');button.click();}})()''')


async def fill(evaluate, selector: str, value: str) -> None:
    """通过真实输入事件更新表单。@param evaluate CDP求值器。@param selector 控件。@param value 合成值。@return 无。"""
    await evaluate(f'''(() => {{const input=document.querySelector({json.dumps(selector)});
        input.value={json.dumps(value)};input.dispatchEvent(new Event('input',{{bubbles:true}}));
        input.dispatchEvent(new Event('change',{{bubbles:true}}));}})()''')
    await evaluate('new Promise(resolve=>requestAnimationFrame(resolve))')


async def time_value(evaluate, wait_for, label: str, value: str) -> None:
    """通过统一时间气泡确认时分。@param evaluate CDP求值器。@param wait_for 条件等待。@param label 控件名。@param value 时分。@return 无。"""
    await evaluate(f'document.querySelector({json.dumps("button[aria-label=" + json.dumps(label,ensure_ascii=False) + "]")}).click()')
    await wait_for('Boolean(document.querySelector(".fui-clock"))')
    hour, minute = value.split(':')
    await fill(evaluate, '.fui-clock .fui-field:first-child input', hour)
    await fill(evaluate, '.fui-clock .fui-field:last-child input', minute)
    await click_text(evaluate, '.fui-clock button', '确认')
    await wait_for('!document.querySelector(".fui-clock")')


async def navigate(evaluate, wait_for, tab: str, account_id=None) -> None:
    """通过原生入口进入任务分区及账号。@param evaluate CDP求值器。@param wait_for 条件等待。@param tab 分区。@param account_id 可选账号。@return 无。"""
    if await evaluate('location.pathname') != '/tasks':
        await evaluate('document.querySelector(".console-sidebar a[href=\\"/tasks\\"]").click()')
        await wait_for('location.pathname==="/tasks" && Boolean(document.querySelector(".task-runtime[aria-busy=false]"))')
    selector = '.task-runtime [data-tab=' + json.dumps(tab) + ']'
    await wait_for(f'Boolean(document.querySelector({json.dumps(selector)}))')
    await evaluate(f'document.querySelector({json.dumps(selector)}).click()')
    await evaluate('new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)))')
    await wait_for(f'document.querySelector({json.dumps(selector)}).classList.contains("active")')
    if account_id is not None:
        await wait_for(f'Boolean(document.querySelector("#projects-account option[value=\\"{account_id}\\"]"))')
        await wait_for('!document.querySelector("#projects-account").disabled')
        await fill(evaluate, '#projects-account', str(account_id))


async def open_run(evaluate, wait_for, run_id: str) -> None:
    """从运行记录打开或重开详情。@param evaluate CDP求值器。@param wait_for 条件等待。@param run_id 记录。@return 无。"""
    await evaluate('document.querySelector(".approved-run-dialog [data-slot=dialog-close]")?.click()')
    await wait_for('!document.querySelector(".approved-run-dialog")')
    await navigate(evaluate, wait_for, 'runs')
    selector = '[data-detail=' + json.dumps(run_id) + ']'
    await wait_for(f'Boolean(document.querySelector({json.dumps(selector)}))')
    await evaluate(f'document.querySelector({json.dumps(selector)}).click()')
    await wait_for('Boolean(document.querySelector(".approved-run-dialog .run-followups"))')
    await wait_for('document.querySelector(".approved-run-dialog .run-detail-footer").textContent.includes("更新于")')
