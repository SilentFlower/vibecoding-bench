"""验证真实代理组件及账号选线，网络和写入全部使用合成回执。"""
import asyncio
import copy
import json
import re
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit, parse_qs, unquote
from playwright.async_api import async_playwright, expect
from verify_accounts_design import AccountDesignFixture
from verify_environment_ui import BASE, ROOT


class ProxyDesignFixture(AccountDesignFixture):
    """提供分页目录、CAS与只读引用。"""

    def __init__(self):
        """初始化21条独立线路。@return 无。"""
        super().__init__()
        self.proxies = [dict(id=f'proxy-{i}',name=f'线路 {i}',protocol='http',host=f'proxy{i}.example.test',port=8080,
            public_url=f'http://proxy{i}.example.test:8080',has_username=True,has_password=True,
            expires_at=(datetime.now(timezone.utc)+timedelta(days=5)).isoformat(),revision='revision-1',status='ready',
            checked_at='2026-11-15T02:00:00Z',observation=dict(ip=f'203.0.113.{i}',country='新加坡',country_code='SG',region='新加坡',city='新加坡',latency_ms=42,observed_at='2026-11-15T02:00:00Z'),
            users=[],references_complete=True,active_accounts=0,in_flight=0) for i in range(1,22)]
        self.proxies[0]['users']=[dict(kind='gateway',id='1',name='正式账号 1',status='active',in_flight=1)]
        self.proxies[0].update(active_accounts=1,in_flight=1)
        self.accounts[0].update(proxy_id='proxy-1',proxy_name='线路 1')
        self.proxy_template=copy.deepcopy(self.proxies[-1])
        self.next_proxy_id=22
        self.proxy_reads=[]
        self.fail_probe=False

    @staticmethod
    def parse_connection(text):
        """识别预览地址，私有字段只回到提交表单。@param text 合成连接。@return 拆分字段。"""
        raw=text.strip()
        match=re.fullmatch(r'([^:\s@/]+):(\d+):([^:]*):(.*)',raw)
        if match:
            value=dict(protocol='http',host=match[1],port=int(match[2]),username=match[3],password=match[4])
        else:
            parsed=urlsplit(raw if '://' in raw else 'http://'+raw)
            if not parsed.hostname or parsed.path not in ('','/') or parsed.query or parsed.fragment:raise ValueError()
            if '://' not in raw and not re.search(r':\d+/?$',raw):raise ValueError()
            value=dict(protocol=parsed.scheme,host=parsed.hostname,port=parsed.port or (80 if parsed.scheme=='http' else 1080),username=unquote(parsed.username or ''),password=unquote(parsed.password or ''))
        if value['protocol'] not in ('http','socks5','socks5h') or not 1<=value['port']<=65535:raise ValueError()
        return value

    async def route(self, route):
        """精确模拟管理边界，保留其他模块原夹具。@param route 请求。@return 无。"""
        req=route.request; url=urlsplit(req.url); path=url.path; body=req.post_data_json if req.post_data else {}
        if path=='/proxies': return await route.fulfill(path=str(ROOT/'apps/web/dist/index.html'),content_type='text/html')
        if path.startswith('/admin/proxies'):
            for row in self.proxies:
                row['users']=[dict(kind='gateway',id=str(a['id']),name=a['name'],status=a['status'],in_flight=a.get('active_requests',0)) for a in self.accounts if a.get('proxy_id')==row['id']]
                row['active_accounts']=sum(user['in_flight']>0 for user in row['users'])
                row['in_flight']=sum(user['in_flight'] for user in row['users'])
            if req.method!='GET': self.writes.append(dict(path=path,method=req.method,body=body))
            if path=='/admin/proxies/identify':
                try:return await self.respond(route,self.parse_connection(body['text']))
                except ValueError:return await self.respond(route,{'error':'代理格式无效'},400)
            if path=='/admin/proxies/import':
                values=[]
                for index,line in enumerate(body['text'].splitlines()):
                    if not line.strip():continue
                    try:
                        parsed=self.parse_connection(line)
                        value=copy.deepcopy(self.proxy_template);value.update(id=f'proxy-{self.next_proxy_id+len(values)}',name=parsed['host'],protocol=parsed['protocol'],host=parsed['host'],port=parsed['port'],public_url=f"{parsed['protocol']}://{parsed['host']}:{parsed['port']}",status='unknown',observation=None,checked_at=None,expires_at=None,users=[],has_username=bool(parsed['username']),has_password=bool(parsed['password']))
                        values.append(value)
                    except ValueError:return await self.respond(route,{'error':f'第{index+1}行代理格式无效'},400)
                if not 1<=len(values)<=200:return await self.respond(route,{'error':'每次导入1～200条代理'},400)
                self.next_proxy_id+=len(values);self.proxies.extend(values)
                return await self.respond(route,{'created':len(values)})
            if path=='/admin/proxies' and req.method=='GET':
                query=parse_qs(url.query); page=int(query.get('page',['1'])[0]); size=int(query.get('page_size',['20'])[0]); search=query.get('q',[''])[0].lower()
                self.proxy_reads.append(query)
                rows=[p for p in self.proxies if search in (p['name']+' '+p['public_url']+' '+(p.get('observation') or {}).get('ip','')+' '+(p.get('observation') or {}).get('country','')).lower()]
                return await self.respond(route,dict(data=rows[(page-1)*size:page*size],total=len(rows),page=page,page_size=size,total_pages=(len(rows)+size-1)//size,references_complete=True,counts=dict(all=len(self.proxies),available=sum(p['status']=='ready' for p in self.proxies),used=sum(bool(p['users']) for p in self.proxies))))
            if path=='/admin/proxies' and req.method=='POST':
                row=copy.deepcopy(self.proxy_template); row.update(body,id=f'proxy-{self.next_proxy_id}',users=[],observation=None,status='unknown',checked_at=None); self.next_proxy_id+=1
                row['public_url']=f"{body['protocol']}://{body['host']}:{body['port']}"; row['has_username']=bool(row.pop('username','')); row['has_password']=bool(row.pop('password','')); self.proxies.append(row)
                return await self.respond(route,{'id':row['id']})
            match=re.fullmatch(r'/admin/proxies/([^/]+)(/probe)?',path)
            if match:
                row=next(p for p in self.proxies if p['id']==match[1])
                if match[2]:
                    row['status']='failed' if self.fail_probe else 'ready'
                    return await self.respond(route,{key:row[key] for key in ['id','status','observation','checked_at']})
                if body.get('revision')!=row['revision']: return await self.respond(route,{'error':'代理已被修改，请刷新后重新编辑'},400)
                if req.method=='DELETE':
                    if row['users']: return await self.respond(route,{'error':'线路正在被账号或登录草稿使用'},400)
                    self.proxies.remove(row); return await self.respond(route,{'ok':True})
                changed=any(body.get(key,row[key])!=row[key] for key in ['protocol','host','port'])
                row.update(body,revision=row['revision']+'x',sync_pending=bool(row['users']) and changed)
                row['public_url']=f"{row['protocol']}://{row['host']}:{row['port']}"
                if 'username' in row:row['has_username']=bool(row.pop('username'))
                if 'password' in row:row['has_password']=bool(row.pop('password'))
                return await self.respond(route,{'id':row['id'],'sync_pending':row.get('sync_pending',False)})
        match=re.fullmatch(r'/admin/accounts/(\d+)',path)
        if match and req.method=='GET': return await self.respond(route,next(a for a in self.accounts if a['id']==int(match[1])))
        if match and req.method=='PUT' and 'proxy_id' in body:
            account=next(a for a in self.accounts if a['id']==int(match[1])); proxy=next((p for p in self.proxies if p['id']==body['proxy_id']),None)
            account.update(proxy_id=proxy['id'] if proxy else None,proxy_name=proxy['name'] if proxy else None,proxy_url=proxy['public_url'] if proxy else '')
        return await super().route(route)


async def main():
    """覆盖公开显示、保存取消、过期、分页和账号草稿。@return 无。"""
    out=ROOT/'.deploy/frontend-sidebar-refresh/proxies'; out.mkdir(parents=True,exist_ok=True)
    fixture=ProxyDesignFixture(); errors=[]
    async with async_playwright() as p:
        browser=await p.chromium.launch()
        context=await browser.new_context(viewport={'width':1440,'height':1000})
        await context.route('**/*',fixture.route)
        await context.add_init_script("localStorage.setItem('claude-code-gateway_auth','synthetic-only')")
        page=await context.new_page(); page.on('pageerror',lambda error:errors.append(str(error)))
        await page.goto(BASE+'/proxies')
        await expect(page.locator('tr[data-proxy-id]')).to_have_count(20)
        await expect(page.locator('.proxy-page')).not_to_contain_text('secret')
        await page.get_by_role('searchbox',name='搜索代理',exact=True).fill('线路 21')
        await expect(page.locator('tr[data-proxy-id]')).to_have_count(1)
        await expect(page.locator('tr[data-proxy-id]')).to_contain_text('线路 21')
        await page.get_by_role('searchbox',name='搜索代理',exact=True).fill('')
        await expect(page.locator('tr[data-proxy-id]')).to_have_count(20)
        row=page.locator('[data-proxy-id="proxy-2"]')
        await row.get_by_role('button',name='编辑',exact=True).click()
        dialog=page.locator('.proxy-editor')
        await expect(dialog.get_by_role('spinbutton',name='端口',exact=True)).to_have_value('8080')
        await dialog.get_by_role('button',name='延长 30 天').click()
        await dialog.get_by_role('button',name='取消',exact=True).click()
        assert not fixture.writes
        await row.get_by_role('button',name='编辑',exact=True).click()
        await dialog.get_by_role('button',name='延长 90 天').click()
        await dialog.get_by_role('button',name='保存代理').click()
        await expect(dialog).to_have_count(0)
        saved=fixture.writes[-1]['body']; assert 'username' not in saved and 'password' not in saved
        assert datetime.fromisoformat(saved['expires_at'].replace('Z','+00:00')) > datetime.now(timezone.utc)+timedelta(days=94)
        await row.get_by_role('button',name='编辑',exact=True).click()
        await dialog.get_by_label('一键识别代理',exact=True).fill('socks5://demo:secret@host.example.test:1080')
        await dialog.get_by_role('button',name='识别填入').click()
        await expect(dialog.get_by_role('combobox',name='代理类型')).to_contain_text('SOCKS5')
        await expect(dialog.locator('input[type=password]').last).to_have_value('secret')
        await dialog.get_by_role('button',name='到期时间').click()
        calendar=page.locator('.fui-calendar'); await expect(calendar).to_be_visible()
        await calendar.get_by_role('button',name='下个月').click()
        await page.keyboard.press('Escape'); await expect(calendar).to_have_count(0); await expect(dialog).to_be_visible()
        for width in [1440,720,390]:
            await page.set_viewport_size({'width':width,'height':1000})
            await page.screenshot(path=str(out/f'editor-{width}.png'))
            assert await dialog.evaluate('e=>e.scrollWidth<=e.clientWidth+1')
        await dialog.get_by_role('button',name='取消',exact=True).click()
        for width in [1440,720,390]:
            await page.set_viewport_size({'width':width,'height':1000}); assert await page.evaluate('document.documentElement.scrollWidth<=innerWidth')
            await page.screenshot(path=str(out/f'list-{width}.png'),full_page=True)
        await page.set_viewport_size({'width':1440,'height':1000})
        fixture.fail_probe=True
        await row.get_by_role('button',name='检测',exact=True).click(); await expect(row).to_contain_text('检测失败'); await expect(row).to_contain_text('上次成功结果')
        used=page.locator('[data-proxy-id="proxy-1"]')
        await used.get_by_role('button',name='编辑',exact=True).click(); await expect(dialog.get_by_role('spinbutton',name='端口',exact=True)).to_be_enabled(); await dialog.get_by_role('spinbutton',name='端口',exact=True).fill('9090'); await dialog.get_by_role('button',name='保存代理',exact=True).click(); await expect(dialog).to_have_count(0); await expect(used.get_by_role('status')).to_contain_text('关联同步中'); await used.get_by_role('button',name='编辑',exact=True).click(); await expect(dialog.get_by_role('spinbutton',name='端口',exact=True)).to_be_disabled(); await dialog.get_by_role('button',name='取消',exact=True).click(); fixture.proxies[0]['sync_pending']=False
        await used.get_by_role('button',name='删除',exact=True).click(); await page.get_by_role('button',name='确认删除',exact=True).click(); await expect(page.get_by_role('alert')).to_contain_text('正在被账号'); await page.keyboard.press('Escape')
        await used.locator('.proxy-user-chips').get_by_role('button',name='正式账号 1',exact=True).click()
        workspace=page.locator('.account-workspace'); await expect(workspace).to_be_visible()
        await workspace.locator('.proxy-picker-trigger').click()
        popup=page.locator('.proxy-picker-popup'); await expect(popup).to_be_visible()
        await popup.get_by_role('searchbox',name='搜索代理线路',exact=True).fill('线路 21')
        await expect(popup.get_by_role('button',name=re.compile('线路 21'))).to_be_visible()
        await popup.get_by_role('button',name=re.compile('线路 21')).click()
        writes=len(fixture.writes)
        await workspace.get_by_role('button',name='取消',exact=True).click(); assert len(fixture.writes)==writes
        assert page.url==BASE+'/proxies'; await used.locator('.proxy-user-chips').get_by_role('button',name='正式账号 1',exact=True).click()
        await workspace.locator('.proxy-picker-trigger').click(); await popup.get_by_role('searchbox',name='搜索代理线路',exact=True).fill('线路 21'); await popup.get_by_role('button',name=re.compile('线路 21')).click()
        await workspace.get_by_role('button',name='保存修改',exact=True).click(); await expect(workspace).to_have_count(0)
        assert fixture.writes[-1]['body']=={'proxy_id':'proxy-21','proxy_revision':'revision-1'},fixture.writes[-1]
        assert page.url==BASE+'/proxies'
        assert not errors,errors
        result=dict(passed=True,checks=['跨页搜索','编辑取消零写入','延长90天','凭据缺省保留','一键识别','日期组件Esc层级','使用中连接编辑与同步状态','删除使用保护','失败保留上次观测','账号跨页选线与增量保存','1440/720/390px'],errors=errors)
        (out/'verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)); print(json.dumps(result,ensure_ascii=False)); await browser.close()


if __name__=='__main__': asyncio.run(main())
