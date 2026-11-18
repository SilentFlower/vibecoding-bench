"""用真实构建页面验证新账号节点选择、原草稿节点展示及默认本机兼容。"""
from __future__ import annotations

import asyncio
import json
import re
from urllib.parse import urlsplit

from playwright.async_api import async_playwright, expect

from verify_cluster_ui import select
from verify_environment_ui import BASE, ROOT
from verify_task_login_design import LoginFixture


class DraftNodeFixture(LoginFixture):
    """沿原任务页面夹具提供合成节点，所有写入保持离线。"""

    def __init__(self) -> None:
        """保存只读准备阶段的观察次数。:return: None。"""
        super().__init__()
        self.status_reads=0

    async def route(self, route) -> None:
        """返回固定节点和草稿，其它路径复用原代理与登录夹具。

        :param route: 当前浏览器请求。
        :return: None。
        """
        path=urlsplit(route.request.url).path
        if path=='/runtime/api/accounts/login/start' and not self.fail_start:
            self.login_calls.append(route.request.post_data_json)
            return await self.respond(route,{'session_id':'synthetic-login','ws_path':'/api/accounts/login/ws/synthetic-login',
                'has_sidecar':False,'name':route.request.post_data_json['name'],'reconnectable':False,
                'environment_id':'f'*32,'draft_generation':'a'*32,'node_id':2,'node_name':'合成执行节点'})
        if path=='/runtime/api/accounts/login/synthetic-login/status':
            self.status_reads+=1
            preparing=self.status_reads<3
            return await self.respond(route,{'phase':'preparing' if preparing else 'authorizing',
                'reconnectable':not preparing,'credentials_ready':False,'authorization_url':None,
                'message':'原节点正在准备登录' if preparing else '终端正在等待授权'})
        if path=='/runtime/api/nodes':
            return await self.respond(route,{'items':[
                {'id':1,'kind':'local','name':'默认本机','enabled':True},
                {'id':2,'kind':'ssh','name':'合成执行节点','enabled':True,'preparation':{'state':'prepared'}},
                {'id':3,'kind':'ssh','name':'待准备节点','enabled':True,'preparation':None}]})
        if path=='/runtime/api/environments':
            row={**self.rows[0],'environment_id':'e'*32,'name':'node-draft','account_id':None,'gateway_account_id':None,
                'login_draft':True,'node':{'node_id':2,'node_key':'a'*32,'node_name':'原草稿节点 <demo>',
                    'kind':'ssh','enabled':True},'role_status':{'cli':'running','sender':'unknown','network':'unknown'},
                'can_reprofile':False,'busy':False,'native_preparation':None,'native_kernel':None,
                'criu':None,'content_capture':None,'run_window':None}
            row.pop('physical_features',None)
            return await self.respond(route,[row])
        if path=='/runtime/api/accounts/login-drafts':
            return await self.respond(route,[{'environment_id':'e'*32,'name':'node-draft','generation':'d'*32,
                'node_id':2,'node_name':'原草稿节点 <demo>','state':'cancelled','session_id':None,
                'credentials_present':True,'credentials_ready':False,'can_resume':True,'can_restart':True,
                'can_delete':True,'can_reconcile':False,'proxy_known':True,'proxy_summary':None}])
        return await super().route(route)


async def run() -> None:
    """检查实际可见选择器、数值载荷、草稿转义和三种视口。

    :return: None；证据写入隔离目录。
    """
    output=ROOT/'.deploy/cluster-draft-ui'
    output.mkdir(parents=True,exist_ok=True)
    fixture,errors=DraftNodeFixture(),[]
    async with async_playwright() as playwright:
        browser=await playwright.chromium.launch()
        context=await browser.new_context(viewport={'width':1440,'height':1000})
        await context.route('**/*',fixture.route)
        await context.add_init_script("localStorage.setItem('claude-code-gateway_auth','synthetic-only')")
        page=await context.new_page()
        sockets=[]
        await page.route_web_socket(re.compile('.*'),lambda websocket:(sockets.append(websocket),websocket.on_message(lambda _:None)))
        page.on('pageerror',lambda error:errors.append(str(error)))
        await page.goto(BASE+'/tasks')
        workspace=page.locator('.task-runtime')
        await expect(workspace.locator('#work-login-drafts')).to_contain_text('执行节点：原草稿节点 <demo>')
        await expect(workspace.locator('#work-login-drafts demo')).to_have_count(0)
        await workspace.locator('#add-account').click()
        modal=workspace.locator('#acc-modal')
        await expect(modal.locator('#acc-node-note')).to_contain_text('按需选择服务器')
        await select(page,'执行节点','合成执行节点')
        await modal.locator('[name=name]').fill('remote-new')
        await modal.get_by_role('button',name='开始授权',exact=True).click()
        await expect(page.locator('.fui-toast-stack')).to_contain_text('合成登录暂不可用')
        assert fixture.login_calls[-1]['node_id']==2,fixture.login_calls
        assert isinstance(fixture.login_calls[-1]['node_id'],int)
        for width in (1440,720,390):
            await page.set_viewport_size({'width':width,'height':1000})
            assert await modal.evaluate('element=>element.scrollWidth<=element.clientWidth')
            await page.screenshot(path=str(output/f'node-config-{width}.png'),full_page=True)
        await modal.locator('#acc-modal-close').click()
        await workspace.locator('#add-account').click()
        await expect(modal.locator('#acc-node-note')).to_contain_text('按需选择服务器')
        await modal.locator('[name=name]').fill('default-new')
        await modal.get_by_role('button',name='开始授权',exact=True).click()
        await expect(page.locator('.fui-toast-stack')).to_contain_text('合成登录暂不可用')
        assert 'node_id' not in fixture.login_calls[-1],fixture.login_calls
        await modal.locator('#acc-modal-close').click()
        fixture.fail_start=False
        await workspace.locator('#add-account').click()
        await expect(modal.locator('#acc-node-note')).to_contain_text('按需选择服务器')
        await select(page,'执行节点','合成执行节点')
        await modal.locator('[name=name]').fill('prepared-remote')
        await modal.get_by_role('button',name='开始授权',exact=True).click()
        await expect(modal.locator('#acc-login-name')).to_contain_text('合成执行节点')
        await expect(modal.locator('#acc-login-connection-status')).to_contain_text('终端已连接',timeout=10000)
        assert fixture.status_reads>=3,fixture.status_reads
        assert len(sockets)==1,len(sockets)
        await modal.get_by_role('button',name='取消登录',exact=True).click()
        await expect(modal).to_be_hidden()
        await page.set_viewport_size({'width':1440,'height':1000})
        await page.goto(BASE+'/environments')
        card=page.locator('article[data-environment="'+'e'*32+'"]')
        await expect(card).to_contain_text('登录草稿')
        await card.get_by_role('button',name='资源与采集',exact=True).click()
        environment=page.locator('.runtime-environment-dialog')
        await expect(environment).to_contain_text('请在任务账号页继续登录或完整清理')
        await expect(environment.locator('.workspace-panel-layout')).to_have_count(0)
        for width in (1440,390):
            await page.set_viewport_size({'width':width,'height':1000})
            assert await environment.evaluate('element=>element.scrollWidth<=element.clientWidth')
            await page.screenshot(path=str(output/f'draft-environment-{width}.png'),full_page=True)
        assert not errors,errors
        await browser.close()
    result={'passed':True,'scenes':['节点数值载荷','默认本机兼容','草稿节点名称与转义','准备阶段持续轮询后连接一次原会话','草稿环境只读及节点位置','1440/720/390布局'],
        'errors':errors,'real_model_requests':0}
    (output/'results.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
    print(json.dumps(result,ensure_ascii=False))


if __name__=='__main__':
    asyncio.run(run())
