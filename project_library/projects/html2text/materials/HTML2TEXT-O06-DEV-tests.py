"""严格配置真实作用于转换器，拼写错误与冲突在转换前拒绝。"""
from html2text import HTML2Text
import pytest

def test_mapping_is_immutable_detached_and_applies_actual_conversion():
    """配置可复用但调用者/转换器均不能反写其值。@return None。"""
    from html2text import Options
    original={'body_width':0,'ignore_links':True,'images_to_alt':True};options=Options.from_mapping(original);original['ignore_links']=False
    converter=HTML2Text.from_options(options,baseurl='https://e.test/')
    assert converter.handle('<a href="x">link</a> <img src="pic" alt="Alt">').strip()=='link Alt'
    converter.ignore_links=False;assert options.as_dict()['ignore_links'] is True
    values=options.as_dict();values['ignore_links']=False;assert options.as_dict()['ignore_links'] is True
    with pytest.raises(AttributeError):options._values={}

def test_unknown_types_ranges_and_conflicting_modes_fail_before_use():
    """不让拼写错误静默成为无效动态属性。@return None。"""
    from html2text import Options
    for values in [{'ignroe_links':True},{'body_width':-1},{'body_width':True},{'images_to_alt':True,'images_as_html':True},{'single_line_break':True,'body_width':20}]:
        with pytest.raises(ValueError):Options.from_mapping(values)
    with pytest.raises(TypeError):Options.from_mapping({'ignore_links':'yes'})
    with pytest.raises(TypeError):HTML2Text.from_options({})

def test_defaults_legacy_attributes_two_instances_and_callback_are_compatible():
    """默认配置与原构造一致，两个实例及原out/baseurl参数各自生效。@return None。"""
    from html2text import Options
    text='<p>before <a href="path">link</a></p>'
    options=Options.from_mapping({});assert HTML2Text.from_options(options).handle(text)==HTML2Text().handle(text)
    first=HTML2Text.from_options(Options.from_mapping({'body_width':0,'single_line_break':True}));second=HTML2Text.from_options(options)
    first.ignore_links=True;assert not second.ignore_links
    output=[];converter=HTML2Text.from_options(Options.from_mapping({'body_width':0}),out=output.append,baseurl='https://e.test/')
    converter.handle(text);assert 'https://e.test/path' in ''.join(output)
