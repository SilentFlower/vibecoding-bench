"Public regression tests for SQLPARSE-02-DEV; the complete business contract is in materials/SQLPARSE-02-DEV-contract.md."
import contextlib
import io
import tempfile
import unittest
from pathlib import Path
import sqlparse
from sqlparse.cli import create_parser,main


def test_literals_switches_and_last_argument_wins():
    "Verify literals switches and last argument wins."
    parser=create_parser()
    for option,field in (('--comma_first','comma_first'),('--compact','compact')):
        for value,expected in (('True',True),('false',False),('1',True),('0',False)):
            assert getattr(parser.parse_args(['a.sql',option,value]),field) is expected
        assert getattr(parser.parse_args(['a.sql',option]),field) is True
    assert parser.parse_args(['a.sql','--compact','--no-compact']).compact is False
    with contextlib.redirect_stderr(io.StringIO()),unittest.TestCase().assertRaises(SystemExit):parser.parse_args(['a.sql','--compact','maybe'])


def test_actual_cli_uses_false_and_true_in_formatting():
    "Verify actual cli uses false and true in formatting."
    with tempfile.TemporaryDirectory() as temporary:
        path=Path(temporary)/'query.sql';text='select a,b,c from t';path.write_text(text)
        for value in ('False','True'):
            output=io.StringIO()
            with contextlib.redirect_stdout(output):assert main([str(path),'-r','--comma_first',value])==0
            assert output.getvalue()==sqlparse.format(text,reindent=True,comma_first=value=='True')

