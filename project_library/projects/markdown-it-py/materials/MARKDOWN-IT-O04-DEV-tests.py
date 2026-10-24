"Public regression tests for MARKDOWN-IT-O04-DEV; the complete business contract is in materials/MARKDOWN-IT-O04-DEV-contract.md."
from markdown_it.cli.parse import main,convert_file,convert_stdin
from io import TextIOWrapper,BytesIO
import pytest

def test_explicit_strict_file_failure_has_source_position_and_no_document(tmp_path,capsys):
    "Verify explicit strict file failure has source position and no document."
    path=tmp_path/'bad.md';path.write_bytes(b'secret-before\xffafter')
    with pytest.raises(SystemExit) as error:main(['--encoding-errors','strict',str(path)])
    output=capsys.readouterr()
    assert error.value.code==1 and output.out=='' and str(path) in output.err and '13' in output.err
    assert 'secret-before' not in output.err and 'after' not in output.err

def test_explicit_replace_ignore_and_valid_unicode_remain_available(tmp_path,capsys):
    "Verify explicit replace ignore and valid unicode remain available."
    path=tmp_path/'input.md';path.write_bytes(b'before\xffafter')
    assert main([str(path)])==0
    assert capsys.readouterr().out=='<p>beforeafter</p>\n'
    assert main(['--encoding-errors','replace',str(path)])==0
    assert 'before\ufffdafter' in capsys.readouterr().out
    assert main(['--encoding-errors','ignore',str(path)])==0
    assert 'beforeafter' in capsys.readouterr().out
    path.write_text('# 你好',encoding='utf8');main([str(path)]);assert '<h1>你好</h1>' in capsys.readouterr().out

def test_raw_stdin_uses_same_policy_and_invalid_policy_is_rejected(monkeypatch,capsys):
    "Verify raw stdin uses same policy and invalid policy is rejected."
    import sys
    monkeypatch.setattr(sys,'stdin',TextIOWrapper(BytesIO(b'a\xffb'),encoding='utf8',errors='ignore'))
    with pytest.raises(SystemExit):convert_stdin(errors='strict')
    assert capsys.readouterr().out==''
    monkeypatch.setattr(sys,'stdin',TextIOWrapper(BytesIO(b'a\xffb'),encoding='utf8'))
    main(['--stdin','--encoding-errors','replace']);assert 'a\ufffdb' in capsys.readouterr().out
    with pytest.raises(SystemExit):main(['--encoding-errors','unknown'])
