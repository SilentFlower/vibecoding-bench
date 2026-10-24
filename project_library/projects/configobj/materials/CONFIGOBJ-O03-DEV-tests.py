"""原子发布使用真实ConfigObj编码及同目录替换。"""
from configobj import ConfigObj
import pytest
import os

def test_publish_roundtrip_mode_and_original_state(tmp_path):
    """已有模式和注释保持，原配置对象不被序列化污染。@return None。"""
    path=tmp_path/'app.ini';path.write_text('old=yes\n');path.chmod(0o640)
    config=ConfigObj(['# title','x=杭州'],encoding='utf8');old_indent=config.indent_type
    assert config.write_atomic(path)==path.absolute()
    assert ConfigObj(str(path),encoding='utf8')['x']=='杭州' and path.stat().st_mode&0o777==0o640
    assert config.indent_type==old_indent and config.filename is None

def test_replace_failure_keeps_old_and_cleans(tmp_path,monkeypatch):
    """替换失败不破坏旧字节且只清理本轮临时文件。@return None。"""
    path=tmp_path/'app.ini';path.write_bytes(b'old=1\n')
    def fail(*args):raise OSError('replace failed')
    monkeypatch.setattr(os,'replace',fail)
    with pytest.raises(OSError):ConfigObj({'x':'2'}).write_atomic(path)
    assert path.read_bytes()==b'old=1\n' and list(tmp_path.iterdir())==[path]

def test_new_file_mode_and_symlink_rejection(tmp_path):
    """新文件私有模式，符号链接明确拒绝。@return None。"""
    config=ConfigObj({'x':'1'});path=tmp_path/'new';config.write_atomic(path)
    assert path.stat().st_mode&0o777==0o600
    link=tmp_path/'link';link.symlink_to(path)
    with pytest.raises(ValueError):config.write_atomic(link)
