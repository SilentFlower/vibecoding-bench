"""公开临时进程环境回归。"""
import os
import pytest
from dotenv.environment import temporary_environment

def test_values_and_absence_are_restored(monkeypatch):
    monkeypatch.setenv('DOTENV_SCOPE_A','old')
    monkeypatch.delenv('DOTENV_SCOPE_B', raising=False)
    with temporary_environment({'DOTENV_SCOPE_A':'new','DOTENV_SCOPE_B':'created'}, override=True) as keys:
        assert keys == ('DOTENV_SCOPE_A','DOTENV_SCOPE_B')
        assert os.environ['DOTENV_SCOPE_A'] == 'new'
    assert os.environ['DOTENV_SCOPE_A']=='old' and 'DOTENV_SCOPE_B' not in os.environ

def test_exception_and_nested_scope_restore_each_boundary(monkeypatch):
    monkeypatch.setenv('DOTENV_SCOPE_A','old')
    with pytest.raises(LookupError):
        with temporary_environment({'DOTENV_SCOPE_A':'outer'}, override=True):
            with temporary_environment({'DOTENV_SCOPE_A':'inner'}, override=True):
                assert os.environ['DOTENV_SCOPE_A']=='inner'
            assert os.environ['DOTENV_SCOPE_A']=='outer'
            raise LookupError()
    assert os.environ['DOTENV_SCOPE_A']=='old'

def test_none_and_override_are_explicit(monkeypatch):
    monkeypatch.setenv('DOTENV_SCOPE_A','old')
    with temporary_environment({'DOTENV_SCOPE_A':None}):
        assert os.environ['DOTENV_SCOPE_A']=='old'
    with temporary_environment({'DOTENV_SCOPE_A':None}, override=True, remove_none=True):
        assert 'DOTENV_SCOPE_A' not in os.environ
    assert os.environ['DOTENV_SCOPE_A']=='old'

def test_invalid_late_key_prevents_any_write(monkeypatch):
    monkeypatch.delenv('DOTENV_SCOPE_B', raising=False)
    with pytest.raises(ValueError):
        with temporary_environment({'DOTENV_SCOPE_B':'new','BAD=NAME':'bad'}):
            pass
    assert 'DOTENV_SCOPE_B' not in os.environ
