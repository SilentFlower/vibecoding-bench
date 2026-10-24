"Public regression tests for SQLPARSE-06-DEV; the complete business contract is in materials/SQLPARSE-06-DEV-contract.md."
import contextlib
import io
import tempfile
import unittest
from pathlib import Path
import sqlparse
from sqlparse.exceptions import SQLParseError


def test_strict_unknown_key_suggestion_and_supported_manifest():
    "Verify strict unknown key suggestion and supported manifest."
    with unittest.TestCase().assertRaises(SQLParseError) as raised:sqlparse.format('select 1',strict_options=True,keyword_cases='upper')
    assert 'keyword_cases' in str(raised.exception) and 'keyword_case' in str(raised.exception)
    with unittest.TestCase().assertRaises(SQLParseError):sqlparse.format('select 1',strict_options=True,typo=None)
    assert sqlparse.format('select 1',strict_options=True,keyword_case='upper')=='SELECT 1'
    assert isinstance(sqlparse.formatter.SUPPORTED_OPTIONS,frozenset)


def test_default_compatibility_and_cli_metadata():
    "Verify default compatibility and cli metadata."
    assert sqlparse.format('select 1',keyword_cases='upper')=='select 1'
    with tempfile.TemporaryDirectory() as temporary:
        path=Path(temporary)/'query.sql';path.write_text('select 1')
        output=io.StringIO()
        with contextlib.redirect_stdout(output):assert sqlparse.cli.main([str(path),'-k','upper'])==0
        assert output.getvalue()=='SELECT 1'
    with unittest.TestCase().assertRaises(SQLParseError):sqlparse.format('select 1',strict_options='yes')

