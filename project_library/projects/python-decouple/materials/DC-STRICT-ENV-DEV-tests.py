"""严格ENV模式定位坏行且不暴露配置值。"""
import pytest
from decouple import RepositoryEnv


def test_strict_rejects_malformed(tmp_path):
    """坏行包含行号与路径，不回显敏感文本。@param tmp_path 临时目录。@return None。"""
    path = tmp_path / 'settings.env'
    path.write_text('# comment\nPRIVATE-NO-EQUALS\n', encoding='utf-8')
    with pytest.raises(ValueError) as result:
        RepositoryEnv(str(path), strict=True)
    assert '2' in str(result.value) and str(path) in str(result.value)
    assert 'PRIVATE-NO-EQUALS' not in str(result.value)


def test_strict_duplicate_and_empty(tmp_path):
    """重复和空键不会默默覆盖。@param tmp_path 临时目录。@return None。"""
    path = tmp_path / 'settings.env'
    for content in ['A=1\nA=2', '=empty']:
        path.write_text(content, encoding='utf-8')
        with pytest.raises(ValueError):
            RepositoryEnv(str(path), strict=True)


def test_default_tolerant_and_valid_strict(tmp_path):
    """默认宽容不变，严格模式读取合法空值及引用。@param tmp_path 临时目录。@return None。"""
    path = tmp_path / 'settings.env'
    path.write_text('BAD\nA=1\nA=2', encoding='utf-8')
    assert RepositoryEnv(str(path))['A'] == '2'
    path.write_text('A=\nB="x=y"', encoding='utf-8')
    repository = RepositoryEnv(str(path), strict=True)
    assert repository['A'] == '' and repository['B'] == 'x=y'
