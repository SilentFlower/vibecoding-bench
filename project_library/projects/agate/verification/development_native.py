"""独立业务验收：仅调用候选真实库API，不读取候选测试或参考补丁。"""
import json
import os
from pathlib import Path

import agate

def tab(rows, names):
    """创建冻结类型的合成表。@param rows 数据。@param names 列名。@return Table。"""
    return agate.Table(rows, names, [agate.Text()] * len(names))

def composite():
    """检查组合键、重复匹配与行序。@return bool。"""
    left = tab([('q','west'),('x','east')], ['product','market'])
    right = tab([('q','west','a'),('q','west','b'),('x','east','c')], ['item','area','name'])
    expect = [('q','west','a'),('q','west','b'),('x','east','c')]
    return all([tuple(row) for row in left.join(right, [0,1], keys).rows] == expect
        for keys in ([0,1], ['item',1], [-3,-2], ['item','area']))

def identity():
    """检查等值右列实际身份。@return bool。"""
    left = tab([('11',),('22',)], ['customer'])
    right = tab([('11','11','A'),('22','22','B')], ['duplicate','key','value'])
    return all(left.join(right,0,key).column_names == ('customer','duplicate','value')
        and tuple(left.join(right,0,key).rows[0]) == ('11','11','A') for key in ('key',1,-2))

def boundaries():
    """检查显式投影、外连接与无匹配。@return bool。"""
    left = tab([('m','r'),('n','s')], ['id','zone'])
    right = tab([('m','r','M'),('o','t','O')], ['key','area','value'])
    projected = left.join(right,[0,1],[0,1],columns=['key','value'])
    outer = left.join(right,[0,1],[0,1],full_outer=True)
    inner = left.join(right,[0,1],[0,1],inner=True)
    return (tuple(projected.rows[1]) == ('n','s',None,None)
        and projected.column_names == ('id','zone','key','value')
        and tuple(outer.rows[-1]) == (None,None,'o','t','O') and len(inner.rows) == 1)

def controls():
    """检查调用型键与原表不变。@return bool。"""
    left = tab([('v',)], ['id'])
    right = tab([('v','payload')], ['key','value'])
    joined = left.join(right,lambda r:r[0],lambda r:r[0])
    return joined.column_names == ('id','key','value') and right.column_names == ('key','value')

CHECKS = {'composite_identifiers':composite, 'equal_values_column_identity':identity,
    'projection_outer_unmatched':boundaries, 'callable_controls':controls}
MODULE = agate
MODULE_FILE = 'library/agate/__init__.py'
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
