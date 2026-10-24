"Public regression tests for DC-FACTORY-DEV; the complete business contract is in materials/DC-FACTORY-DEV-contract.md."
import pytest
from decouple import Config, RepositoryEmpty


def test_factory_late_cast(monkeypatch):
    "Verify factory late cast."
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
    "Verify factory conflict and callable default."
    config = Config(RepositoryEmpty())
    value = lambda: 1
    assert config('DEVELOPMENT_MISSING', default=value) is value
    with pytest.raises(ValueError):
        config('DEVELOPMENT_MISSING', default=1, default_factory=value)


def test_factory_recursion_and_none():
    "Verify factory recursion and none."
    config = Config(RepositoryEmpty())
    def recursive():
        "Support the public regression through recursive."
        return config('DEVELOPMENT_RECURSIVE', default_factory=recursive)
    with pytest.raises(ValueError):
        config('DEVELOPMENT_RECURSIVE', default_factory=recursive)
    assert config('DEVELOPMENT_RECURSIVE', default_factory=lambda: None) is None
