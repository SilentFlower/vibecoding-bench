"""默认工厂只在所有来源缺失时执行一次。"""
import pytest
from decouple import Config, RepositoryEmpty


def test_factory_late_cast(monkeypatch):
    """环境存在或空值时均不执行工厂。@param monkeypatch 环境隔离。@return None。"""
    config = Config(RepositoryEmpty())
    calls = []
    factory = lambda: calls.append(1) or '8'
    monkeypatch.delenv('DEVELOPMENT_FACTORY', raising=False)
    assert config('DEVELOPMENT_FACTORY', default_factory=factory, cast=int) == 8
    assert calls == [1]
    monkeypatch.setenv('DEVELOPMENT_FACTORY', '')
    assert config('DEVELOPMENT_FACTORY', default_factory=factory) == ''
    assert calls == [1]


def test_factory_conflict_and_callable_default():
    """旧可调用default仍是值，双重默认政策拒绝。@return None。"""
    config = Config(RepositoryEmpty())
    value = lambda: 1
    assert config('DEVELOPMENT_MISSING', default=value) is value
    with pytest.raises(ValueError):
        config('DEVELOPMENT_MISSING', default=1, default_factory=value)


def test_factory_recursion_and_none():
    """递归不无限执行，None是合法后备值。@return None。"""
    config = Config(RepositoryEmpty())
    def recursive():
        """重入相同键。@return 不返回。"""
        return config('DEVELOPMENT_RECURSIVE', default_factory=recursive)
    with pytest.raises(ValueError):
        config('DEVELOPMENT_RECURSIVE', default_factory=recursive)
    assert config('DEVELOPMENT_RECURSIVE', default_factory=lambda: None) is None
