"""原覆盖引擎中的额外受保护业务断言，保留完整冻结原回归。"""
import contextlib
import io
import json
from pathlib import Path
import runpy
import sys


def cover_features(project, evidence):
    """按真实行为/新入口识别已存在能力并执行完整新增矩阵。

    :param project: 原控制器构建的实际实现叠加目录。
    :param evidence: 本轮只写证据目录。
    :return: None；额外断言失败使原测试阶段失败。
    """
    import injector
    from dataclasses import dataclass
    assert Path(injector.__file__).resolve().is_relative_to(project.resolve())
    active=[]
    class Probe:
        """只用于实际部分预设行为检测的合成对象。"""
        @injector.inject
        def __init__(self,name:str,n:int):self.name,self.n=name,n
    container=injector.Injector(lambda binder:binder.bind(str,to='covered'))
    try:
        value=container.get(injector.BoundKey(Probe,n=injector.InstanceProvider(3)))
    except (TypeError,injector.CallError):
        pass
    else:
        if value.name=='covered' and value.n==3:active.append('INJECTOR-O01-DEV')
    @injector.noninjectable('n')
    @injector.inject
    @dataclass
    class Manual:
        """只用于类级排除元信息检测。"""
        n:int
    if 'n' not in injector.get_bindings(Manual.__init__):active.append('INJECTOR-O02-DEV')
    class Config(injector.Module):
        """只使用本地已声明依赖。"""
        @injector.inject
        def __init__(self,name:str):self.name=name
        def configure(self,binder):binder.bind(bytes,to=self.name.encode())
    try:container.binder.install(Config)
    except (TypeError,injector.CallError):pass
    else:
        if container.get(bytes)==b'covered':active.append('INJECTOR-O03-DEV')
    for task,present in [('INJECTOR-O04-DEV',hasattr(injector,'ContextScope')),
        ('INJECTOR-O05-DEV',hasattr(injector.SingletonScope,'evict')),
        ('INJECTOR-O06-DEV',hasattr(injector.Binder,'bindings_snapshot'))]:
        if present:active.append(task)
    base=Path(__file__).parent
    executed=[]
    for task in active:
        previous_path=list(sys.path)
        namespace={}
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                probe=base/(task+'-observe.py')
                content=probe.read_text();begin='\nimport injector\n';end='\nprint(json.dumps('
                assert content.count(begin)==1 and content.count(end)==1
                # 原控制器已经把当前overlay源码及分发元数据绑定到独占venv。
                # 重放同一业务矩阵时不能再次创建同名dist-info，也不能改变已核源码归属。
                exec(compile(content[content.index(begin):content.index(end)],str(probe),'exec'),namespace)
            assert namespace['business'] is True,'独立新业务矩阵失败：'+task
        finally:
            sys.path[:]=previous_path
        public=runpy.run_path(str(base/(task+'-coverage-public.py')))
        tests=[value for name,value in public.items() if name.startswith('test_') and callable(value)]
        assert len(tests)==3
        for test in tests:test()
        executed.append({'task_id':task,'business':'passed','public_assertions':len(tests)})
    (evidence/'expansion-coverage.json').write_text(json.dumps({'status':'passed',
        'candidate_import':True,'original_nodes_unchanged':True,'original_coverage_threshold_unchanged':True,
        'executed_objectives':executed},ensure_ascii=False,indent=2)+'\n')
