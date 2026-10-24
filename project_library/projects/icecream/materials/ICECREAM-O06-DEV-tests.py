"""只在合成builtin名上验证归属恢复，不触碰print等真实内置功能。"""
import builtins
from icecream import IceCreamDebugger
import pytest
NAME='_bench_managed_icecream'

def test_restore_existing_and_remove_missing_on_exception(monkeypatch):
    """旧值恢复，不存在名字最终移除，异常仍传播。@return None。"""
    from icecream.builtins import managed_install
    old=object();monkeypatch.setattr(builtins,NAME,old,raising=False)
    debug=IceCreamDebugger()
    with managed_install(NAME,debug) as handle:assert getattr(builtins,NAME) is debug
    assert getattr(builtins,NAME) is old;handle.close()
    monkeypatch.delattr(builtins,NAME)
    with pytest.raises(ValueError):
        with managed_install(NAME,debug):raise ValueError('business')
    assert not hasattr(builtins,NAME)

def test_same_debugger_nested_out_of_order_close(monkeypatch):
    """同一debugger也以安装token区分归属，乱序关闭不复活旧层。@return None。"""
    from icecream.builtins import managed_install
    old=object();monkeypatch.setattr(builtins,NAME,old,raising=False);debug=IceCreamDebugger()
    outer=managed_install(NAME,debug);inner=managed_install(NAME,debug)
    outer.close();assert getattr(builtins,NAME) is debug
    inner.close();assert getattr(builtins,NAME) is old

def test_foreign_replacement_and_invalid_names(monkeypatch):
    """另一组件中途替换的值不被撤销，非法名不写入。@return None。"""
    from icecream.builtins import managed_install
    monkeypatch.delattr(builtins,NAME,raising=False);handle=managed_install(NAME);foreign=object();setattr(builtins,NAME,foreign)
    handle.close();assert getattr(builtins,NAME) is foreign
    with pytest.raises(RuntimeError):handle.__enter__()
    for name in ['', 'a.b', 'class']:
        with pytest.raises(ValueError):managed_install(name)
