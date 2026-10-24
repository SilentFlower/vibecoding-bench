"Public regression tests for PA-ITER-LINES-DEV; the complete business contract is in materials/PA-ITER-LINES-DEV-contract.md."
from path import Path
import pytest

def test_universal_and_original_line_endings_are_explicit(tmp_path):
    path=Path(tmp_path/'text');path.write_bytes(b'a\r\nb\rc\nlast')
    assert list(path.iter_lines())==['a\n','b\n','c\n','last']
    assert list(path.iter_lines(newline=''))==['a\r\n','b\r','c\n','last']

def test_blank_lines_and_unicode_survive_without_terminators(tmp_path):
    path=Path(tmp_path/'text');path.write_bytes('雪\r\n\r\n花'.encode())
    assert list(path.iter_lines(encoding='utf-8',retain=False,newline=''))==['雪','','花']

def test_early_close_closes_the_actual_file(tmp_path,monkeypatch):
    path=Path(tmp_path/'text');path.write_text('a\nb\n');original=Path.open;streams=[]
    def opened(self,*args,**kwargs):
        stream=original(self,*args,**kwargs);streams.append(stream);return stream
    monkeypatch.setattr(Path,'open',opened)
    rows=path.iter_lines();assert next(rows)=='a\n';rows.close()
    assert streams[0].closed

def test_decode_errors_are_propagated_or_explicitly_replaced(tmp_path):
    path=Path(tmp_path/'text');path.write_bytes(b'bad\xff\n')
    with pytest.raises(UnicodeDecodeError):
        list(path.iter_lines(encoding='utf-8'))
    assert list(path.iter_lines(encoding='utf-8',errors='replace'))==['bad\ufffd\n']
