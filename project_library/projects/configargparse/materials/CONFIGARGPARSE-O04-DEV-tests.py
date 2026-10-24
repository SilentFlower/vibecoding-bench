"""配置源预览不会执行提供器、打开文件或改解析状态。"""
from pathlib import Path
import configargparse as c

def test_preview_order_and_real_open_matches(tmp_path):
    """匹配路径和重复来源按真实glob顺序出现。@return None。"""
    a=tmp_path/'a.ini';b=tmp_path/'b.ini';a.write_text('x=1');b.write_text('x=2')
    p=c.ArgumentParser(default_config_files=[tmp_path/'*.ini',a])
    rows=p.discover_config_files();streams=p._open_config_files([])
    try: assert [r['path'] for r in rows if r.get('exists')]==[label for stream,label in streams]
    finally:
        for stream,label in streams:stream.close()
    assert rows[-1]['path']==str(a) and rows[-1]['index']==1

def test_provider_not_called_and_missing_explicit(tmp_path):
    """缺路径有记录，提供器绝不执行。@return None。"""
    def forbidden():raise AssertionError('provider executed')
    p=c.ArgumentParser(default_config_files=[tmp_path/'missing',forbidden])
    assert p.discover_config_files()==[{'kind':'path','index':0,'path':str(tmp_path/'missing'),'exists':False},{'kind':'provider','index':1,'executed':False}]

def test_open_function_and_pathlike_precedence(tmp_path):
    """同时callable和PathLike的声明按路径处理且不打开。@return None。"""
    class Both:
        def __fspath__(self):return str(tmp_path/'x')
        def __call__(self):raise AssertionError('called')
    def forbidden(*args):raise AssertionError('opened')
    p=c.ArgumentParser(default_config_files=[Both()],config_file_open_func=forbidden)
    assert p.discover_config_files()[0]['kind']=='path'
