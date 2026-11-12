"Public regression tests for PYTHON-MARKDOWN-05-DEV; the complete business contract is in materials/PYTHON-MARKDOWN-05-DEV-contract.md."
from markdown.results import convert_document


def test_actual_metadata_toc_and_reference_snapshot():
    "Verify actual metadata toc and reference snapshot."
    result=convert_document('title: 中文\n\n# Heading\n\n[link][ref]\n\n[ref]: https://example.com "Title"',extensions=['markdown.extensions.meta','markdown.extensions.toc'])
    assert '<h1 id="heading">Heading</h1>' in result.html
    assert result.metadata=={'title':['中文']} and result.toc_tokens[0]['id']=='heading'
    assert result.references['ref']==('https://example.com','Title') and '#heading' in result.toc


def test_result_defaults_and_later_calls_are_independent():
    "Verify result defaults and later calls are independent."
    first=convert_document('# One',extensions=['markdown.extensions.toc']);first.toc_tokens[0]['name']='changed'
    second=convert_document('# Two',extensions=['markdown.extensions.toc'])
    assert second.toc_tokens[0]['name']=='Two'
    plain=convert_document('plain')
    assert plain.html=='<p>plain</p>' and plain.metadata=={} and plain.toc_tokens==[] and plain.toc=='' and plain.references=={}

