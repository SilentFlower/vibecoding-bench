"Public regression tests for CK-STABLE-WRITE-DEV; the complete business contract is in materials/CK-STABLE-WRITE-DEV-contract.md."
import pytest
import click
from click.testing import CliRunner
from click.writing import write_if_changed

def test_equal_bytes_keep_inode_mtime_and_mode(tmp_path):
    path=tmp_path/'out';path.write_bytes(b'same');path.chmod(0o640);before=path.stat()
    assert write_if_changed(path,'same') is False
    after=path.stat()
    assert (after.st_ino,after.st_mtime_ns,after.st_mode)==(before.st_ino,before.st_mtime_ns,before.st_mode)

def test_changed_content_and_encoding_roundtrip(tmp_path):
    path=tmp_path/'out'
    assert write_if_changed(path,'雪',encoding='utf-16') and path.read_bytes()=='雪'.encode('utf-16')
    assert path.stat().st_mode&0o777==0o600

def test_replace_failure_preserves_old_bytes_and_cleans_temp(tmp_path,monkeypatch):
    path=tmp_path/'out';path.write_text('old')
    def broken(*args):
        raise OSError('synthetic')
    monkeypatch.setattr('os.replace',broken)
    with pytest.raises(OSError):
        write_if_changed(path,'new')
    assert path.read_text()=='old' and list(tmp_path.iterdir())==[path]

def test_real_command_reports_whether_generation_changed(tmp_path):
    path=tmp_path/'out'
    @click.command()
    def command():
        click.echo('changed' if write_if_changed(path,'content') else 'unchanged')
    runner=CliRunner()
    assert runner.invoke(command).output.strip()=='changed'
    assert runner.invoke(command).output.strip()=='unchanged'
