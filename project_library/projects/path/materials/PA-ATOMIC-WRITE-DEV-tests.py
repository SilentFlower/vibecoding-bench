"""公开Path原子发布回归。"""
import pytest
from path import Path

def test_changed_and_unchanged_outputs_have_distinct_effects(tmp_path):
    path=Path(tmp_path/'out');assert path.atomic_write('雪')
    before=path.stat()
    assert path.atomic_write('雪',if_changed=True) is False
    after=path.stat();assert (before.st_ino,before.st_mtime_ns,before.st_mode)==(after.st_ino,after.st_mtime_ns,after.st_mode)
    assert path.atomic_write(b'new') and path.read_bytes()==b'new'

def test_original_mode_and_new_private_mode_are_preserved(tmp_path):
    path=Path(tmp_path/'out');path.atomic_write('a');assert path.stat().st_mode&0o777==0o600
    path.chmod(0o640);path.atomic_write('b');assert path.stat().st_mode&0o777==0o640

def test_replace_failure_preserves_old_file_and_cleans_temp(tmp_path,monkeypatch):
    path=Path(tmp_path/'out');path.write_text('old')
    def broken(*args):
        raise OSError('synthetic')
    monkeypatch.setattr('os.replace',broken)
    with pytest.raises(OSError):
        path.atomic_write('new')
    assert path.read_text()=='old' and sorted(p.name for p in tmp_path.iterdir())==['out']

def test_encoding_failure_and_symlink_rejection_do_not_modify_target(tmp_path):
    path=Path(tmp_path/'out');path.write_text('old')
    with pytest.raises(UnicodeEncodeError):
        path.atomic_write('雪',encoding='ascii')
    link=tmp_path/'link';link.symlink_to(path)
    with pytest.raises(ValueError):
        Path(link).atomic_write('bad')
    assert path.read_text()=='old'
