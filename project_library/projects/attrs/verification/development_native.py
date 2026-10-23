"""独立业务验收：仅调用候选真实库API，不读取候选测试或参考补丁。"""
import json
import os
from pathlib import Path

import attr
import attrs
from attr.filters import _split_what, include, exclude

def fields():
    """生成三个相等但身份独立的字段。@return 字段列表。"""
    return [attr.fields(attr.make_class(name,{'key':attr.ib(default=4)})).key for name in ('One','Two','Three')]

def identity():
    """对象相等不等于选中。@return bool。"""
    a,b,c = fields()
    return (a == b and a is not b and include(a)(a,4) and not include(a)(b,4)
        and not exclude(a)(a,4) and exclude(a)(b,4) and not include(a)(a.evolve(),4))

def multiple():
    """等值参数不能被集合合并丢失。@return bool。"""
    a,b,c = fields()
    return ([include(a,b)(field,4) for field in (a,b,c)] == [True,True,False]
        and [exclude(a,b)(field,4) for field in (a,b,c)] == [False,False,True]
        and _split_what((a,b))[2] == frozenset((a,b)) and hash(a) == hash(b))

def branches():
    """保持字段名和精确值类型语义。@return bool。"""
    a,b,c = fields()
    return (include('key')(b,4) and include(a,str)(b,'other') and not include(int)(b,True)
        and not include()(a,4) and exclude()(b,4) and not exclude('key')(c,4))

def integration():
    """真实对象导出与继承保持同一规则。@return bool。"""
    one = attr.make_class('Invoice', {'key':attr.ib(default=4),'value':attr.ib(default='x')})
    two = attr.make_class('Copy', {'key':attr.ib(default=4),'value':attr.ib(default='x')})
    selected = attr.fields(one).key
    child = attr.s(type('Child',(one,),{}))
    inherited = attr.fields(child).key
    return (all(api.asdict(two(),filter=include(selected)) == {} and api.astuple(two(),filter=exclude(selected)) == (4,'x')
        and api.asdict(one(),filter=include(selected)) == {'key':4} for api in (attr,attrs))
        and include(selected)(inherited,4) == (inherited is selected))

CHECKS = {'exact_attribute_identity':identity,'multiple_equal_arguments':multiple,'name_and_type_branches':branches,'exports_and_inheritance':integration}
MODULE = attr
MODULE_FILE = 'library/src/attr/__init__.py'
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
