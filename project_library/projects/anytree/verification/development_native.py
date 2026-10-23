"""独立业务验收：仅调用候选真实库API，不读取候选测试或参考补丁。"""
import json
import os
from pathlib import Path

import io
from collections import OrderedDict
import anytree
from anytree import Node
from anytree.exporter import DictExporter, JsonExporter

def root():
    """创建独立的三层目录。@return Node。"""
    node = Node('目录')
    child = Node('正文',parent=node)
    Node('段落',parent=child)
    return node

def reuse():
    """摘要不会截断后续字典输出。@return bool。"""
    shared = DictExporter()
    node = root()
    before = shared.export(node)
    preview = json.loads(JsonExporter(shared,maxlevel=1).export(node))
    return preview == {'name':'目录'} and shared.maxlevel is None and shared.export(node) == before

def depths():
    """write、无覆盖和连续覆盖均保持共享深度。@return bool。"""
    shared = DictExporter(maxlevel=2)
    node = root()
    stream = io.StringIO()
    JsonExporter(shared,maxlevel=1).write(node,stream)
    deep = json.loads(JsonExporter(shared,maxlevel=3).export(node))
    inherited = json.loads(JsonExporter(shared).export(node))
    return (json.loads(stream.getvalue()) == {'name':'目录'} and shared.maxlevel == 2
        and deep['children'][0]['children'][0]['name'] == '段落'
        and 'children' not in inherited['children'][0])

def custom():
    """普通子类及原回调保持。@return bool。"""
    class Exporter(DictExporter):
        """含简单实例状态的自定义导出器。@return 实例。"""
        def export(self,node):
            """扩展结果。@param node 根。@return 字典。"""
            data = super().export(node)
            data['custom'] = self.tag
            return data
    attrs = lambda pairs: sorted(pairs)
    children = lambda nodes: reversed(nodes)
    shared = Exporter(dictcls=OrderedDict,attriter=attrs,childiter=children,maxlevel=9)
    shared.tag = 'kept'
    result = json.loads(JsonExporter(shared,maxlevel=1).export(root()))
    return (result == {'name':'目录','custom':'kept'} and shared.maxlevel == 9
        and shared.attriter is attrs and shared.childiter is children and shared.dictcls is OrderedDict)

def failure():
    """异常路径保留原深度。@return bool。"""
    def broken(values):
        """模拟业务回调失败。@param values 属性。@return 不返回。"""
        raise LookupError('expected')
    shared = DictExporter(attriter=broken,maxlevel=4)
    try:
        JsonExporter(shared,maxlevel=1).write(root(),io.StringIO())
    except LookupError:
        return shared.maxlevel == 4 and shared.attriter is broken
    return False

CHECKS = {'shared_depth_isolated':reuse,'write_and_depth_order':depths,'custom_exporter_preserved':custom,'exception_preserves_configuration':failure}
MODULE = anytree
MODULE_FILE = 'library/src/anytree/__init__.py'
def main():
    """逐项捕获业务不满足并输出稳定事实。@return None。"""
    root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()
    result = {'candidate_import':Path(MODULE.__file__).resolve() == root / MODULE_FILE}
    for name, check in CHECKS.items():
        try:
            result[name] = bool(check())
        except Exception:
            result[name] = False
    print(json.dumps(result, sort_keys=True))

if __name__ == '__main__':
    main()
