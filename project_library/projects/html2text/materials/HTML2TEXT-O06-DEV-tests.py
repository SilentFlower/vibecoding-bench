"Public regression tests for HTML2TEXT-O06-DEV; the complete business contract is in materials/HTML2TEXT-O06-DEV-contract.md."
from html2text import HTML2Text
import pytest

def test_mapping_is_immutable_detached_and_applies_actual_conversion():
    "Verify mapping is immutable detached and applies actual conversion."
    from html2text import Options
    original={'body_width':0,'ignore_links':True,'images_to_alt':True};options=Options.from_mapping(original);original['ignore_links']=False
    converter=HTML2Text.from_options(options,baseurl='https://e.test/')
    assert converter.handle('<a href="x">link</a> <img src="pic" alt="Alt">').strip()=='link Alt'
    converter.ignore_links=False;assert options.as_dict()['ignore_links'] is True
    values=options.as_dict();values['ignore_links']=False;assert options.as_dict()['ignore_links'] is True
    with pytest.raises(AttributeError):options._values={}

def test_unknown_types_ranges_and_conflicting_modes_fail_before_use():
    "Verify unknown types ranges and conflicting modes fail before use."
    from html2text import Options
    for values in [{'ignroe_links':True},{'body_width':-1},{'body_width':True},{'images_to_alt':True,'images_as_html':True},{'single_line_break':True,'body_width':20}]:
        with pytest.raises(ValueError):Options.from_mapping(values)
    with pytest.raises(TypeError):Options.from_mapping({'ignore_links':'yes'})
    with pytest.raises(TypeError):HTML2Text.from_options({})

def test_defaults_legacy_attributes_two_instances_and_callback_are_compatible():
    "Verify defaults legacy attributes two instances and callback are compatible."
    from html2text import Options
    text='<p>before <a href="path">link</a></p>'
    options=Options.from_mapping({});assert HTML2Text.from_options(options).handle(text)==HTML2Text().handle(text)
    first=HTML2Text.from_options(Options.from_mapping({'body_width':0,'single_line_break':True}));second=HTML2Text.from_options(options)
    first.ignore_links=True;assert not second.ignore_links
    output=[];converter=HTML2Text.from_options(Options.from_mapping({'body_width':0}),out=output.append,baseurl='https://e.test/')
    converter.handle(text);assert 'https://e.test/path' in ''.join(output)
