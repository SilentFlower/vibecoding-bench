"""目录控制属性只排除该目录项，不丢标题、锚点或后代正文。"""
import markdown


def test_opt_in_exclusion_keeps_heading_and_promotes_children():
    """排除标题仍有id和permalink，子节继续进入目录。@return None。"""
    md=markdown.Markdown(extensions=['markdown.extensions.toc','markdown.extensions.attr_list'],extension_configs={'markdown.extensions.toc':{'unlisted_attribute':'data-toc-unlisted','permalink':True}})
    output=md.convert('# Visible\n\n## Hidden {data-toc-unlisted}\n\n### Child\n\nBody')
    assert 'id="hidden"' in output and 'Hidden' in output and 'Body' in output
    assert 'data-toc-unlisted' not in output
    assert md.toc_tokens[0]['children'][0]['name']=='Child'
    assert 'Hidden' not in md.toc and 'Child' in md.toc


def test_default_and_attribute_retention_policy():
    """默认关闭保持旧TOC，控制属性保留由选项决定。@return None。"""
    text='# Heading {data-toc-unlisted=true}'
    normal=markdown.Markdown(extensions=['markdown.extensions.toc','markdown.extensions.attr_list']);normal.convert(text)
    assert normal.toc_tokens[0]['name']=='Heading'
    md=markdown.Markdown(extensions=['markdown.extensions.toc','markdown.extensions.attr_list'],extension_configs={'markdown.extensions.toc':{'unlisted_attribute':'data-toc-unlisted','remove_unlisted_attribute':False}})
    output=md.convert(text)
    assert md.toc_tokens==[] and 'data-toc-unlisted="true"' in output

