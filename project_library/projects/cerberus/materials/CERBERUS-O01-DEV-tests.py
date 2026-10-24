"""字段重命名不可删除identity或读取已删除旧键。"""
from cerberus import Validator

def test_identity_keeps_value():
    """rename到自身保持业务值。@return None。"""
    validator = Validator({'x': {'rename': 'x'}})
    assert validator.normalized({'x': 7}) == {'x': 7}

def test_combined_rename_then_handler():
    """两种政策先规划最终名字再移动字段。@return None。"""
    validator = Validator({'x': {'rename': 'target', 'rename_handler': str.upper}}, allow_unknown=True)
    assert validator.normalized({'x': 8}) == {'TARGET': 8}

def test_original_and_handler_failure():
    """输入不改，handler失败沿原错误路径保留值。@return None。"""
    source = {'x': [1]}
    def fail(name):
        """模拟转换失败。@param name 字段名。@return 不返回。"""
        raise ValueError('name')
    validator = Validator({'x': {'rename': 'new', 'rename_handler': fail}}, allow_unknown=True)
    result = validator.normalized(source, always_return_document=True)
    assert source == {'x': [1]} and result == {'x': [1]} and validator.errors
