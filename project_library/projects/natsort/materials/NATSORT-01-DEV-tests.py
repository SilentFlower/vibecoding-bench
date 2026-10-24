"""CLI整数筛选不能把相邻大整数都折为同一个float。"""
import contextlib
import io
from natsort.__main__ import main


def output(*args):
    """捕获实际CLI流水线。@param args 命令参数。@return 输出项。"""
    stream=io.StringIO()
    with contextlib.redirect_stdout(stream):main(*args)
    return stream.getvalue().splitlines()


def test_exclude_adjacent_large_integers():
    """相邻十六位整数独立排除。@return None。"""
    a=2**53
    assert output('--exclude',str(a),'item'+str(a),'item'+str(a+1))==['item'+str(a+1)]


def test_inclusive_range_preserves_exact_boundaries():
    """上下界不提前四舍五入或截断。@return None。"""
    a=2**53
    assert output('--filter',str(a+1),str(a+2),*['x'+str(a+i) for i in range(3)])==['x'+str(a+1),'x'+str(a+2)]
    assert output('--filter','1.5','2.5','x1','x2','x3')==['x2']


def test_float_policy_stays_float():
    """显式浮点策略保留原始筛选。@return None。"""
    assert output('--number-type','float','--filter','1.2','2.9','x3.0','x2.5','x1.5')==['x1.5','x2.5']

