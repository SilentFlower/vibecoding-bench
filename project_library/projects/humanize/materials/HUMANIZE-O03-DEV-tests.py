"""列表可显式选择区域连接规则，默认英语原字节保持。"""
import humanize
from humanize import i18n
import pytest
def catalog(root,word):
    """构造合成GNU消息目录，供实际gettext读取。@return 根路径。"""
    import struct
    entries={'':'Content-Type: text/plain; charset=UTF-8\nLanguage: xx\nPlural-Forms: nplurals=2; plural=(n != 1);\n','one':word,'%s and %s':'%s et %s'}
    pairs=sorted((key.encode(),value.encode()) for key,value in entries.items());count=len(pairs)
    ids=b'\0'.join(key for key,value in pairs)+b'\0';values=b'\0'.join(value for key,value in pairs)+b'\0'
    head=28;id_start=head+count*16;value_start=id_start+len(ids);out=struct.pack('<7I',0x950412de,0,count,head,head+count*8,0,0)
    offset=0
    for key,value in pairs:out+=struct.pack('<2I',len(key),id_start+offset);offset+=len(key)+1
    offset=0
    for key,value in pairs:out+=struct.pack('<2I',len(value),value_start+offset);offset+=len(value)+1
    target=root/'xx'/'LC_MESSAGES'/'humanize.mo';target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(out+ids+values)
    return root

def test_existing_default_and_cardinality_generator():
    """零至多项和一次性生成器完整处理。@return None。"""
    assert humanize.natural_list([])=='' and humanize.natural_list([1])=='1'
    assert humanize.natural_list((str(i) for i in range(3)))=='0, 1 and 2'
    assert humanize.natural_list(['a','b'])=='a and b'

def test_actual_catalog_pattern_and_serial_override(tmp_path):
    """复用原目录已有的双项连接pattern，不写死翻译。@return None。"""
    try:
        i18n.activate('xx',catalog(tmp_path,'uno'))
        assert humanize.natural_list(['a','b','c'],localized=True)=='a, b et c'
        assert humanize.natural_list(['a','b','c'],serial_comma=True)=='a, b, and c'
        assert humanize.natural_list(['a','b'],localized=True)=='a et b'
    finally:i18n.deactivate()

def test_custom_percent_conjunction_unicode_and_validation():
    """自定义连接词作为字面值，不能被当百分号格式。@return None。"""
    assert humanize.natural_list(['杭州','北京'],conjunction='或%')=='杭州 或% 北京'
    with pytest.raises(ValueError):humanize.natural_list(['a','b'],conjunction='')
    with pytest.raises(TypeError):humanize.natural_list(['a','b'],localized=1)
