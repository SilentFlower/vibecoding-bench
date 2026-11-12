"""真实load_file先验证整个路径参数，非法输入不能被silent吞掉。"""
from dynaconf import Dynaconf
from types import ModuleType
import pytest

def test_str_pathlike_and_glob_load_actual_files(tmp_path):
    """文件路径协议与字符串真实读取相同值，glob保留顺序。@return None。"""
    one=tmp_path/'one.json';one.write_text('{"VALUE":1}');two=tmp_path/'two.json';two.write_text('{"VALUE":2}')
    for path in [str(one),one]:
        settings=Dynaconf(environments=False);settings.load_file(path,silent=False);assert settings.VALUE==1
    settings=Dynaconf(environments=False);settings.load_file(str(tmp_path/'*.json'));assert settings.VALUE==2

def test_invalid_arguments_and_mixed_sequence_reject_before_loading(tmp_path):
    """即使silent=True，模块/字典/数字及混合坏项在首文件加载前拒绝。@return None。"""
    path=tmp_path/'one.json';path.write_text('{"VALUE":1}')
    for silent in [True,False]:
        for invalid in [ModuleType('fake'),{},42,b'bytes',[path,42]]:
            settings=Dynaconf(environments=False)
            with pytest.raises(TypeError):settings.load_file(invalid,silent=silent)
            assert settings.get('VALUE') is None

def test_bad_path_protocol_empty_lists_and_no_match_keep_explicit_boundaries():
    """__fspath__结果不合法拒绝，None/空列表/无匹配按旧可选行为。@return None。"""
    class Bad:
        """错误路径协议实现。"""
        def __fspath__(self):return 42
    settings=Dynaconf(environments=False)
    with pytest.raises(TypeError):settings.load_file(Bad())
    assert settings.load_file([]) is None and settings.load_file(None) is None
    assert settings.load_file('unmatched-ordinary-*.json') is None
