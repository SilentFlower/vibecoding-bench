"Public regression tests for HUMANIZE-O03-DEV; the complete business contract is in materials/HUMANIZE-O03-DEV-contract.md."
import humanize
from humanize import i18n
import pytest
def catalog(root,word):
    "Support the public regression through catalog."
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
    "Verify existing default and cardinality generator."
    assert humanize.natural_list([])=='' and humanize.natural_list([1])=='1'
    assert humanize.natural_list((str(i) for i in range(3)))=='0, 1 and 2'
    assert humanize.natural_list(['a','b'])=='a and b'

def test_actual_catalog_pattern_and_serial_override(tmp_path):
    "Verify actual catalog pattern and serial override."
    try:
        i18n.activate('xx',catalog(tmp_path,'uno'))
        assert humanize.natural_list(['a','b','c'],localized=True)=='a, b et c'
        assert humanize.natural_list(['a','b','c'],serial_comma=True)=='a, b, and c'
        assert humanize.natural_list(['a','b'],localized=True)=='a et b'
    finally:i18n.deactivate()

def test_custom_percent_conjunction_unicode_and_validation():
    "Verify custom percent conjunction unicode and validation."
    assert humanize.natural_list(['杭州','北京'],conjunction='或%')=='杭州 或% 北京'
    with pytest.raises(ValueError):humanize.natural_list(['a','b'],conjunction='')
    with pytest.raises(TypeError):humanize.natural_list(['a','b'],localized=1)
