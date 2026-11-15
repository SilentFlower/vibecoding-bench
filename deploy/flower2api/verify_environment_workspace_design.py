"""验证环境左侧分区、内嵌CPU草稿与原CAS提交。"""
import asyncio,json
from urllib.parse import urlsplit
from playwright.async_api import async_playwright,expect
from verify_runtime_workspace_design import WorkspaceFixture
from verify_environment_ui import ROOT,BASE,ENVIRONMENT


class ResourceFixture(WorkspaceFixture):
    """提供真实CPU字段，隔离所有宿主操作。"""
    def __init__(self):
        """创建可编辑角色额度。@return 无。"""
        super().__init__();self.rows[0]['isolation_version']=2;self.cpu={'generation':10,'revision':'cpu-1','host_cpus':8,'cpus':{'cli':2,'sender':1,'network':.5},'persisted_cpus':None}
    async def route(self,route):
        """核对冻结参数和提交值。@param route 请求。@return 无。"""
        if urlsplit(route.request.url).path.endswith('/'+ENVIRONMENT+'/cpu-resources'):
            if route.request.method=='POST':
                body=route.request.post_data_json
                if body['expected_generation']!=10 or body['expected_revision']!=self.cpu['revision']:return await self.respond(route,{'detail':'额度已变化，请重新读取'},409)
                self.writes.append({'path':'cpu-resources','body':body});self.cpu.update(cpus=body['cpus'],revision='cpu-2')
            return await self.respond(route,self.cpu)
        return await super().route(route)


async def main():
    """通过原生环境回归覆盖五分区、CPU草稿、CAS和移动端。@return 无。"""
    from verify_native_environments import run
    result = await run(ROOT / '.deploy/frontend-sidebar-refresh/environment-proxy-audit')
    print(json.dumps(result, ensure_ascii=False))


if __name__=='__main__':asyncio.run(main())
