"""恢复诊断与真实树/编码/兼容模式分开交付，严格模式不伪成功。"""
import html5lib
import pytest

def test_recovering_report_contains_real_tree_errors_encoding_and_quirks():
    """宽容恢复仍保留可用树及每条真实诊断来源。@return None。"""
    from html5lib.diagnostics import parse_with_report
    result=parse_with_report('<p>broken</div>')
    assert result.errors and all(set(error)=={'position','code','details'} for error in result.errors)
    assert result.encoding=='utf-8' and result.compat_mode=='quirks'
    assert 'broken' in ''.join(result.tree.itertext())
    assert html5lib.serialize(result.tree)==html5lib.serialize(html5lib.parse('<p>broken</div>'))

def test_strict_ignore_and_budget_do_not_change_default_parse_contract():
    """error抛原异常、ignore只隐藏报告；上限只截报告不丢真实树。@return None。"""
    from html5lib.diagnostics import parse_with_report
    from html5lib.html5parser import ParseError
    with pytest.raises(ParseError):parse_with_report('<p>x',policy='error')
    ignored=parse_with_report('<p>x',policy='ignore');assert ignored.errors==[] and not ignored.truncated
    limited=parse_with_report('<p>x',max_errors=0);assert limited.errors==[] and limited.truncated and 'x' in ''.join(limited.tree.itertext())

def test_backend_namespaces_valid_documents_and_invalid_policies():
    """DOM后端及无命名空间选项真实生效，合法文档无伪诊断。@return None。"""
    from html5lib.diagnostics import parse_with_report
    result=parse_with_report(b'<!doctype html><html><head><title>T</title></head><body><p>x</p></body></html>',treebuilder='dom',override_encoding='utf8')
    assert result.tree.documentElement.tagName=='html' and result.compat_mode=='no quirks' and result.errors==[]
    bare=parse_with_report('<!doctype html><p>x',namespaceHTMLElements=False);assert bare.tree.tag=='html'
    with pytest.raises(ValueError):parse_with_report('',policy='guess')
    with pytest.raises(ValueError):parse_with_report('',max_errors=True)
