"Public regression tests for DC-STRICT-ENV-DEV; the complete business contract is in materials/DC-STRICT-ENV-DEV-contract.md."
import pytest
from decouple import RepositoryEnv


def test_strict_rejects_malformed(tmp_path):
    "Verify strict rejects malformed."
    path = tmp_path / 'settings.env'
    path.write_text('# comment\nPRIVATE-NO-EQUALS\n', encoding='utf-8')
    with pytest.raises(ValueError) as result:
        RepositoryEnv(str(path), strict=True)
    assert '2' in str(result.value) and str(path) in str(result.value)
    assert 'PRIVATE-NO-EQUALS' not in str(result.value)


def test_strict_duplicate_and_empty(tmp_path):
    "Verify strict duplicate and empty."
    path = tmp_path / 'settings.env'
    for content in ['A=1\nA=2', '=empty']:
        path.write_text(content, encoding='utf-8')
        with pytest.raises(ValueError):
            RepositoryEnv(str(path), strict=True)


def test_default_tolerant_and_valid_strict(tmp_path):
    "Verify default tolerant and valid strict."
    path = tmp_path / 'settings.env'
    path.write_text('BAD\nA=1\nA=2', encoding='utf-8')
    assert RepositoryEnv(str(path))['A'] == '2'
    path.write_text('A=\nB="x=y"', encoding='utf-8')
    repository = RepositoryEnv(str(path), strict=True)
    assert repository['A'] == '' and repository['B'] == 'x=y'
