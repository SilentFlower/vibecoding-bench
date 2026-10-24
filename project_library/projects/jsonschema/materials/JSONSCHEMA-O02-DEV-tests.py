"""JSONPath必须精确指向原始键，不因尾换行选中另一个属性。"""
from jsonschema.exceptions import ValidationError
from jsonschema import Draft202012Validator
import ast

def test_newline_key_is_quoted_escaped_and_resolves_exact_key():
    """用独立字符串字面量解码反查真实键，区分同名无换行属性。@return None。"""
    instance={'x':2,'x\n':1};validator=Draft202012Validator({'properties':{'x\n':{'type':'string'}}})
    error=next(validator.iter_errors(instance));assert error.json_path=="$['x\\n']"
    key=ast.literal_eval(error.json_path[2:-1]);assert key=='x\n' and instance[key]==1

def test_quote_backslash_controls_unicode_and_empty_keys_round_trip():
    """特殊键逐字符往返，输出没有原始C0字符。@return None。"""
    for key in ["a'b",'a\\b','', '\t\r\n\b\f\x00\x1f','中文','2start']:
        error=ValidationError('bad',path=[key]);path=error.json_path
        assert path.startswith("$['") and not any(ord(char)<32 for char in path)
        assert ast.literal_eval(path[2:-1])==key

def test_identifiers_arrays_and_absolute_parent_paths_keep_original_semantics():
    """普通ASCII标识符仍用dot，数组及父错误路径按原绝对顺序。@return None。"""
    child=ValidationError('bad',path=[2,'leaf\n']);parent=ValidationError('outer',path=['root'],context=[child])
    assert child.json_path=="$.root[2]['leaf\\n']" and list(child.absolute_path)==['root',2,'leaf\n']
    assert ValidationError('ok',path=['Alpha_2']).json_path=='$.Alpha_2'
