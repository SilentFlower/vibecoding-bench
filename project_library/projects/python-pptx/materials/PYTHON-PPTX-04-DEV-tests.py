"""段落符号/编号由a:bu*单一选择表达，不能给正文加假编号。"""
from io import BytesIO
import unittest
from pptx import Presentation

def test_character_number_and_none_inheritance_roundtrip():
    """字符与有起点编号真实保存，默认继承不额外创造可见符号。@return None。"""
    presentation=Presentation();frame=presentation.slides.add_slide(presentation.slide_layouts[6]).shapes.add_textbox(0,0,400000,300000).text_frame
    first=frame.paragraphs[0];first.text='first';first.set_bullet('character',character='✓')
    second=frame.add_paragraph();second.text='second';second.set_bullet('number',scheme='romanUcPeriod',start=4)
    output=BytesIO();presentation.save(output);output.seek(0);paragraphs=Presentation(output).slides[0].shapes[0].text_frame.paragraphs
    assert paragraphs[0].bullet=={'kind':'character','character':'✓'}
    assert paragraphs[1].bullet=={'kind':'number','scheme':'romanUcPeriod','start':4} and paragraphs[1].text=='second'

def test_choice_replacement_clear_and_invalid_do_not_change_other_format():
    """切换只保一种符号，None去直接属性，字体/正文不改。@return None。"""
    paragraph=Presentation().slides.add_slide(Presentation().slide_layouts[6]) if False else None
    presentation=Presentation();paragraph=presentation.slides.add_slide(presentation.slide_layouts[6]).shapes.add_textbox(0,0,300000,300000).text_frame.paragraphs[0]
    paragraph.text='item';paragraph.level=2;paragraph.set_bullet('number')
    before=paragraph._p.xml
    with unittest.TestCase().assertRaises(ValueError):paragraph.set_bullet('number',start=0)
    assert paragraph._p.xml==before
    paragraph.set_bullet('none');assert paragraph.bullet=={'kind':'none'}
    paragraph.set_bullet(None);assert paragraph.bullet is None and paragraph.level==2 and paragraph.text=='item'

