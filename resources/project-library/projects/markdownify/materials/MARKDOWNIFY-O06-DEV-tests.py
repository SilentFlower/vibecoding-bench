"Public regression tests for MARKDOWNIFY-O06-DEV; the complete business contract is in materials/MARKDOWNIFY-O06-DEV-contract.md."
from markdownify import MarkdownConverter
from concurrent.futures import ThreadPoolExecutor
import pytest

def test_previously_cached_converter_never_leaks_options_or_binding():
    "Verify previously cached converter never leaks options or binding."
    converter=MarkdownConverter()
    assert converter.convert('<strong>A</strong>')=='**A**'
    before=converter.convert_fn_cache.copy()
    assert converter.convert_with_options('<strong>B</strong>',strip=['strong'])=='B'
    assert converter.convert_with_options('<strong>C</strong>',strong_em_symbol='_')=='__C__'
    assert converter.convert('<strong>D</strong>')=='**D**'
    assert converter.convert_fn_cache==before and converter.options['strip'] is None

def test_custom_constructor_and_nested_container_isolation():
    "Verify custom constructor and nested container isolation."
    callback=lambda el:'plain'
    class Custom(MarkdownConverter):
        "Public regression fixture: Custom."
        def __init__(self,required,**options):
            self.required=required;super().__init__(**options)
        def convert_p(self,el,text,parent_tags):
            assert self.options['code_language_callback'] is callback
            self.options['custom']['values'].append(self.required)
            return self.options['prefix']+text
    converter=Custom('secret',custom={'values':[]},prefix='base:',code_language_callback=callback)
    overrides={'custom':{'values':[]},'prefix':'one:'}
    assert converter.convert_with_options('<p>A</p>',**overrides)=='one:A'
    assert overrides['custom']['values']==[] and converter.options['custom']['values']==[]
    assert converter.options['prefix']=='base:'

def test_parallel_calls_exceptions_and_parser_options_are_isolated():
    "Verify parallel calls exceptions and parser options are isolated."
    converter=MarkdownConverter()
    def convert(symbol):return converter.convert_with_options('<em>x</em>',strong_em_symbol=symbol,bs4_options='html.parser')
    with ThreadPoolExecutor(max_workers=4) as pool:assert list(pool.map(convert,['*','_','*','_']))==['*x*','_x_','*x*','_x_']
    with pytest.raises(ValueError):converter.convert_with_options('<b>x</b>',strip=['b'],convert=['b'])
    assert converter.convert('<em>x</em>')=='*x*' and converter.options['convert'] is None
