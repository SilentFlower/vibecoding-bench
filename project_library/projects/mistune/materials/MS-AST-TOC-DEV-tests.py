"Public regression tests for MS-AST-TOC-DEV; the complete business contract is in materials/MS-AST-TOC-DEV-contract.md."
import mistune
from mistune.toc import add_toc_hook

def test_ast_mode_has_real_toc_items_and_heading_ids():
    md=mistune.create_markdown(renderer='ast');add_toc_hook(md)
    tokens,state=md.parse('# Hello **world**\n')
    assert state.env['toc_items']==[(1,'toc_1','Hello world')] and tokens[0]['attrs']['id']=='toc_1'

def test_nested_selection_is_explicit_and_in_source_order():
    source='# One\n\n> ## Two\n\n### Three\n'
    md=mistune.create_markdown(renderer='ast');add_toc_hook(md,include_nested=True)
    result,state=md.parse(source)
    assert [item[2] for item in state.env['toc_items']]==['One','Two','Three']
    plain=mistune.create_markdown(renderer='ast');add_toc_hook(plain)
    assert [item[2] for item in plain.parse(source)[1].env['toc_items']]==['One','Three']

def test_level_bounds_and_custom_ids_are_preserved():
    md=mistune.create_markdown(renderer='ast');add_toc_hook(md,min_level=2,max_level=2,heading_id=lambda token,index:'custom')
    result,state=md.parse('# Skip\n\n## Included\n')
    assert state.env['toc_items']==[(2,'custom','Included')]

def test_repeated_documents_do_not_inherit_previous_directory():
    md=mistune.create_markdown(renderer='ast');add_toc_hook(md)
    md.parse('# First')
    assert md.parse('plain')[1].env['toc_items']==[]
