"""结果真实来自本次转换的HTML、目录、元数据及引用。"""
from markdown.results import convert_document


def test_actual_metadata_toc_and_reference_snapshot():
    """不凭输入标题拼装结果，使用真实扩展输出。@return None。"""
    result=convert_document('title: 中文\n\n# Heading\n\n[link][ref]\n\n[ref]: https://example.com "Title"',extensions=['markdown.extensions.meta','markdown.extensions.toc'])
    assert '<h1 id="heading">Heading</h1>' in result.html
    assert result.metadata=={'title':['中文']} and result.toc_tokens[0]['id']=='heading'
    assert result.references['ref']==('https://example.com','Title') and '#heading' in result.toc


def test_result_defaults_and_later_calls_are_independent():
    """无扩展字段明确为空，修改快照不会污染其他文档。@return None。"""
    first=convert_document('# One',extensions=['markdown.extensions.toc']);first.toc_tokens[0]['name']='changed'
    second=convert_document('# Two',extensions=['markdown.extensions.toc'])
    assert second.toc_tokens[0]['name']=='Two'
    plain=convert_document('plain')
    assert plain.html=='<p>plain</p>' and plain.metadata=={} and plain.toc_tokens==[] and plain.toc=='' and plain.references=={}

