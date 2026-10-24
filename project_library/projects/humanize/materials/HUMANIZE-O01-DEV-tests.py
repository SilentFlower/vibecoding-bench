"Public regression tests for HUMANIZE-O01-DEV; the complete business contract is in materials/HUMANIZE-O01-DEV-contract.md."
from pathlib import Path
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

def test_two_real_catalog_sources_and_canonical_alias(tmp_path,monkeypatch):
    "Verify two real catalog sources and canonical alias."
    first=catalog(tmp_path/'one','uno');second=catalog(tmp_path/'two','dos')
    try:
        a=i18n.activate('xx',first);assert humanize.apnumber(1)=='uno'
        b=i18n.activate('xx',second);assert humanize.apnumber(1)=='dos' and a is not b
        monkeypatch.chdir(tmp_path)
        assert i18n.activate('xx',Path('one')) is a and humanize.apnumber(1)=='uno'
    finally:i18n.deactivate()

def test_reload_only_current_source_and_failed_load_keeps_active(tmp_path):
    "Verify reload only current source and failed load keeps active."
    first=catalog(tmp_path/'one','uno');second=catalog(tmp_path/'two','dos')
    try:
        a=i18n.activate('xx',first);b=i18n.activate('xx',second)
        catalog(first,'nuevo');assert i18n.activate('xx',first) is a
        assert i18n.activate('xx',first,reload=True).gettext('one')=='nuevo'
        with pytest.raises(FileNotFoundError):i18n.activate('xx',tmp_path/'missing')
        assert humanize.apnumber(1)=='nuevo' and i18n.activate('xx',second) is b
    finally:i18n.deactivate()

def test_default_injected_catalog_and_english_reset(tmp_path,monkeypatch):
    "Verify default injected catalog and english reset."
    import gettext
    with (catalog(tmp_path/'one','uno')/'xx'/'LC_MESSAGES'/'humanize.mo').open('rb') as stream:translation=gettext.GNUTranslations(stream)
    monkeypatch.setitem(i18n._TRANSLATIONS,'xx',translation)
    try:
        assert i18n.activate('xx') is translation
        i18n.activate('en_US');assert humanize.apnumber(1)=='one'
        i18n.activate(None);assert i18n.get_translation().gettext('one')=='one'
    finally:i18n.deactivate()
