"""实际构建的密码节点表单隔离验证。"""
import asyncio,json
from urllib.parse import urlsplit
from playwright.async_api import async_playwright,expect
from verify_environment_ui import Fixture,BASE,ROOT

class NodeFixture(Fixture):
    """合成节点接口沿实际构建页面执行。"""
    async def route(self, route):
        """响应合成节点接口。:param route: 浏览器请求。:return: None。"""
        path=urlsplit(route.request.url).path
        if path=='/nodes':
            return await route.fulfill(content_type='text/html',body=(self.gateway/'index.html').read_text())
        if path=='/admin/accounts':
            # 节点页读取反重力账号以统计本机归属，本场景没有反重力账号。
            return await route.fulfill(content_type='application/json',body=json.dumps({'data':[],'total':0,'page':1,'page_size':100,'total_pages':1}))
        if path.startswith('/runtime/api/nodes'):
            if path.endswith('/host-keys'):
                value={'items':[{'key':'ssh-ed25519 synthetic','algorithm':'ssh-ed25519','sha256':'SHA256:synthetic'}]}
            elif route.request.method=='POST':
                body=route.request.post_data_json
                self.writes.append(body)
                value={'id':2,'node_key':'a'*32,'name':body['name'],'kind':'ssh','revision':1,'enabled':True,'account_count':0,'host':body['host'],'port':22,'username':'root','data_root':body['data_root'],'auth_method':body['auth_method'],'observation':None,'preparation':None}
            else:value={'items':[]}
            return await route.fulfill(content_type='application/json',body=json.dumps(value))
        return await super().route(route)

async def main():
    """验证实际构建的表单交互与凭据清理。:return: None。"""
    fixture=NodeFixture(ROOT/'apps/web/dist'); errors=[]
    async with async_playwright() as p:
        browser=await p.chromium.launch(); context=await browser.new_context(viewport={'width':1440,'height':1000})
        await context.route('**/*',fixture.route)
        await context.add_init_script("localStorage.setItem('claude-code-gateway_auth','synthetic-only')")
        page=await context.new_page();page.on('pageerror',lambda e:errors.append(str(e)))
        await page.goto(BASE+'/nodes')
        await page.get_by_role('button',name='添加节点',exact=True).click()
        dialog=page.get_by_role('dialog')
        await dialog.get_by_label('节点名称',exact=True).fill('密码验证')
        await dialog.get_by_label('服务器地址',exact=True).fill('127.0.0.1')
        await dialog.get_by_label('专用 SSH 私钥',exact=True).fill('synthetic-private-input')
        await dialog.get_by_role('combobox',name='SSH 认证方式',exact=True).click()
        await page.get_by_role('option',name='SSH 密码',exact=True).click()
        await expect(dialog.get_by_label('专用 SSH 私钥',exact=True)).to_have_count(0)
        password=dialog.get_by_label('SSH 密码',exact=True)
        await expect(password).to_have_attribute('type','password')
        secret=' 合成密碼 $`!;\\" 末尾 '
        await password.fill(secret)
        await dialog.get_by_role('combobox',name='SSH 认证方式',exact=True).click()
        await page.get_by_role('option',name='SSH 私钥',exact=True).click()
        await expect(dialog.get_by_label('专用 SSH 私钥',exact=True)).to_have_value('')
        await dialog.get_by_role('combobox',name='SSH 认证方式',exact=True).click()
        await page.get_by_role('option',name='SSH 密码',exact=True).click()
        await expect(password).to_have_value('')
        await password.fill(secret)
        await dialog.get_by_role('button',name='探测主机公钥',exact=True).click()
        await dialog.get_by_role('combobox',name='服务器主机公钥',exact=True).click()
        await page.get_by_role('option',name='ssh-ed25519 · SHA256:synthetic',exact=True).click()
        await dialog.get_by_role('checkbox').check()
        await dialog.get_by_role('button',name='登记节点',exact=True).click()
        await expect(dialog).to_have_count(0)
        assert len(fixture.writes)==1 and fixture.writes[0]['password']==secret
        assert fixture.writes[0]['auth_method']=='password' and 'private_key' not in fixture.writes[0]
        await page.get_by_role('button',name='添加节点',exact=True).click()
        await expect(password).to_have_value('')
        await password.fill(secret)
        await dialog.get_by_role('button',name='取消',exact=True).click()
        await page.get_by_role('button',name='添加节点',exact=True).click()
        await expect(password).to_have_value('')
        for width in (1440,390):
            await page.set_viewport_size({'width':width,'height':1000})
            assert await page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            await page.screenshot(path=str(ROOT/f'.trellis/.runtime/ssh-node-password-auth/form-{width}.png'),full_page=True)
        assert not errors and not fixture.unexpected and not fixture.external,(errors,fixture.unexpected,fixture.external)
        await browser.close()
    print(json.dumps({'passed':True,'scenes':['认证切换清空','密码掩码','原值与单一凭据提交','成功与取消清空','1440/390视口'],'model_requests':0},ensure_ascii=False))

if __name__ == '__main__':
    asyncio.run(main())
