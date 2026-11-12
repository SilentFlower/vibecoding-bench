"""核真实构造、绑定、作用域与异步调用边界。"""
from asyncio import gather, run, sleep
from concurrent.futures import ThreadPoolExecutor
from json import dumps
from os import environ
from pathlib import Path
from sys import argv
from threading import Barrier

import injector
from injector import Error, Injector, UnsatisfiedRequirement, inject, singleton, threadlocal


class Service:
    """只有合成配置名的普通业务服务，默认不缓存实例。"""

    @inject
    def __init__(self, name: str) -> None:
        """保留实际注入值。@param name 合成配置名。@return None。"""
        self.name = name


@singleton
class CachedService(Service):
    """用于观察同一容器内单例生命周期的合成服务。"""


@threadlocal
class FlowContext:
    """仅观察线程身份，不携带任何真实租户或请求数据。"""


def configured(name: str) -> Injector:
    """绑定合成字符串。@param name 配置值。@return 新独立注入器。"""
    result = Injector()
    result.binder.bind(str, to=name)
    return result


def main() -> None:
    """在真实候选与本地对象上核固定业务，不启动服务或访问凭据。@return None。"""
    root = Path(environ['PROJECT_CANDIDATE_ROOT']).resolve()
    result = {'candidate_import': Path(injector.__file__).resolve() == root / 'library/injector/__init__.py'}
    task = argv[1]
    if task == 'IJ-U01':
        first = configured('alpha')
        second = configured('beta')
        a, b = first.get(Service), first.get(Service)
        cached = first.get(CachedService)
        result['no_scope_constructs_while_singleton_caches_per_injector'] = (
            a is not b and a.name == b.name == 'alpha'
            and first.get(CachedService) is cached and second.get(CachedService) is not cached
            and second.get(CachedService).name == 'beta')
    elif task == 'IJ-U02':
        container = configured('provided')
        direct_failed = False
        try:
            Service()
        except TypeError:
            direct_failed = True
        result['constructor_injection_requires_the_injector_call_boundary'] = (
            direct_failed and Service('direct').name == 'direct'
            and container.create_object(Service).name == 'provided'
            and container.create_object(Service, additional_kwargs={'name': 'explicit'}).name == 'explicit')
    elif task == 'IJ-C01':
        permissive = Injector()
        strict = Injector(auto_bind=False)
        strict.binder.bind(Service, to=Service)
        rejected = False
        try:
            strict.get(Service)
        except UnsatisfiedRequirement:
            rejected = True
        strict.binder.bind(str, to='configured')
        result['auto_binding_can_construct_default_values_instead_of_configuration'] = (
            permissive.get(Service).name == '' and rejected and strict.get(Service).name == 'configured')
    elif task == 'IJ-C02':
        container = Injector()
        container.binder.multibind(list[str], to=['alpha'])
        container.binder.multibind(list[str], to=['beta'])
        container.binder.multibind(dict[str, int], to={'limit': 1, 'offset': 0})
        container.binder.multibind(dict[str, int], to={'limit': 2})
        values = container.get(list[str])
        values.append('caller-only')
        member = Service('original')
        container.binder.multibind(list[Service], to=[member])
        container.get(list[Service])[0].name = 'shared'
        rejected = False
        try:
            container.binder.bind(list[str], to=['wrong-entry'])
        except Error:
            rejected = True
        result['multibinding_aggregation_and_duplicate_key_policy_are_explicit'] = (
            container.get(list[str]) == ['alpha', 'beta']
            and container.get(dict[str, int]) == {'limit': 2, 'offset': 0} and rejected
            and container.get(list[Service])[0] is member and member.name == 'shared')
    elif task == 'IJ-P01':
        container = Injector()

        async def flow() -> tuple[FlowContext, FlowContext]:
            """让两个协程在同一线程实际交错。@return 前后上下文对象。"""
            before = container.get(FlowContext)
            await sleep(0)
            return before, container.get(FlowContext)

        async def both() -> list[tuple[FlowContext, FlowContext]]:
            """实际调度两个逻辑请求。@return 两协程的观察。"""
            return await gather(flow(), flow())

        values = run(both())
        barrier = Barrier(2)

        def worker() -> FlowContext:
            """保留两条真实工作线程同时存活。@return 当前线程上下文。"""
            context = container.get(FlowContext)
            barrier.wait(timeout=5)
            return context

        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(worker) for _ in range(2)]
            threaded = [future.result() for future in futures]
        result['thread_local_scope_does_not_isolate_coroutines_on_one_thread'] = (
            values[0][0] is values[0][1] is values[1][0] is values[1][1]
            and threaded[0] is not threaded[1] and all(value is not values[0][0] for value in threaded))
    elif task == 'IJ-D01':
        container = configured('old')
        original = container.get(CachedService)
        container.binder.bind(str, to='new')
        later = container.get(CachedService)
        result.update(original_name=original.name, later_name=later.name, cached_identity_preserved=later is original,
            current_dependency=container.get(str), new_unscoped_service=container.get(Service).name,
            fresh_container_service=configured('new').get(CachedService).name)
    else:
        raise ValueError('未冻结的业务任务')
    print(dumps(result))


if __name__ == '__main__':
    main()
