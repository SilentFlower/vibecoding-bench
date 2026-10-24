"""公开真实原子工作簿文件回归。"""
from zipfile import ZipFile
import pytest
from xlsxwriter.atomic import atomic_workbook

def test_success_replaces_old_file_with_valid_xlsx_and_preserves_mode(tmp_path):
    path=tmp_path/'report.xlsx';path.write_bytes(b'old');path.chmod(0o640)
    with atomic_workbook(path) as book: book.add_worksheet().write(0,0,'new')
    with ZipFile(path) as archive: assert 'xl/worksheets/sheet1.xml' in archive.namelist()
    assert path.stat().st_mode&0o777==0o640 and len(list(tmp_path.iterdir()))==1

def test_body_error_preserves_old_bytes_and_cleans_temp(tmp_path):
    path=tmp_path/'report.xlsx';path.write_bytes(b'old')
    with pytest.raises(RuntimeError):
        with atomic_workbook(path) as book: book.add_worksheet();raise RuntimeError('body')
    assert path.read_bytes()==b'old' and len(list(tmp_path.iterdir()))==1

def test_close_failure_preserves_target(tmp_path,monkeypatch):
    path=tmp_path/'report.xlsx';path.write_bytes(b'old')
    with pytest.raises(RuntimeError,match='close'):
        with atomic_workbook(path) as book:
            monkeypatch.setattr(book,'close',lambda:(_ for _ in ()).throw(RuntimeError('close')))
    assert path.read_bytes()==b'old' and len(list(tmp_path.iterdir()))==1

def test_symlink_is_rejected_and_options_not_mutated(tmp_path):
    target=tmp_path/'target';target.write_bytes(b'old');link=tmp_path/'link';link.symlink_to(target)
    with pytest.raises(ValueError):
        with atomic_workbook(link): pass
    options={'constant_memory':True}
    with atomic_workbook(tmp_path/'new.xlsx',options) as book: book.add_worksheet().write(0,0,1)
    assert options=={'constant_memory':True} and target.read_bytes()==b'old'
