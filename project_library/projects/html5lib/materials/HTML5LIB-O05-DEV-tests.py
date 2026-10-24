"""真实walker文本导出保留文档结构及所有普通tail。"""
import html5lib

def test_paragraphs_breaks_lists_and_entities_follow_reading_order():
    """段落/列表/br不是简单拼接所有Characters。@return None。"""
    from html5lib.text import extract_text
    tree=html5lib.parse('<p>你好 &amp; world<br>next</p><ul><li>one</li><li>two</li></ul><p>after</p>')
    assert extract_text(tree)=='你好 & world\nnext\n\n- one\n- two\n\nafter'

def test_pre_whitespace_tail_inline_and_nested_order_are_not_lost():
    """pre的缩进/空行保留，行内之后tail和后续正文仍完整。@return None。"""
    from html5lib.text import extract_text
    tree=html5lib.parse('<p>before <b>bold</b> tail</p><pre>  a\n\n b  </pre><p>end</p>')
    text=extract_text(tree);assert 'before bold tail' in text and '  a\n\n b  ' in text and text.endswith('end')

def test_dom_etree_hidden_templates_scripts_images_and_input_immutability():
    """两后端结果一致，明确隐藏内容与alt选项真实生效，原树不改。@return None。"""
    from html5lib.text import extract_text
    text='<p>A<img alt="Picture" src="x">B</p><div hidden>secret</div><template>placeholder</template><script>not-body</script><p>C</p>'
    outputs=[]
    for backend in ['etree','dom']:
        tree=html5lib.parse(text,treebuilder=backend);before=html5lib.serialize(tree,tree=backend)
        outputs.append(extract_text(tree,treewalker=backend,include_images=True))
        assert html5lib.serialize(tree,tree=backend)==before
        assert 'secret' in extract_text(tree,treewalker=backend,include_hidden=True)
    assert outputs[0]==outputs[1]=='APictureB\n\nC'
