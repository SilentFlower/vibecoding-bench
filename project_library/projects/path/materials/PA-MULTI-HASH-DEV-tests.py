"""公开单次读取多摘要回归。"""
import hashlib
import pytest
from path import Path

def test_multiple_algorithms_match_exact_binary_data(tmp_path):
    data=bytes(range(256))*7;path=Path(tmp_path/'data');path.write_bytes(data)
    result=path.read_hashes(['sha256','sha512','sha256'],chunk_size=17)
    assert list(result)==['sha256','sha512'] and result=={'sha256':hashlib.sha256(data).hexdigest(),'sha512':hashlib.sha512(data).hexdigest()}

def test_only_one_stream_is_opened(tmp_path,monkeypatch):
    path=Path(tmp_path/'data');path.write_bytes(b'data');original=Path.open;calls=[]
    def opened(self,*args,**kwargs):
        calls.append(str(self))
        return original(self,*args,**kwargs)
    monkeypatch.setattr(Path,'open',opened)
    path.read_hashes(['sha256','sha512'])
    assert calls==[str(path)]

def test_empty_file_and_binary_digest_output(tmp_path):
    path=Path(tmp_path/'empty');path.write_bytes(b'')
    assert path.read_hashes(['sha256'],hex=False)=={'sha256':hashlib.sha256(b'').digest()}

def test_invalid_parameters_fail_before_opening_missing_file(tmp_path):
    path=Path(tmp_path/'absent')
    for algorithms,options in (([],{}),(['not-an-algorithm'],{}),(['shake_128'],{}),(['sha256'],{'chunk_size':True})):
        with pytest.raises((ValueError,TypeError)):
            path.read_hashes(algorithms,**options)
