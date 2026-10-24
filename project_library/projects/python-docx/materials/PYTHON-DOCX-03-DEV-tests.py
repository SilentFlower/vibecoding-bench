"""批注必须先核归属/顺序，再创建部件和范围标记。"""
from io import BytesIO
from zipfile import ZipFile
import unittest
from docx import Document

def test_foreign_empty_reversed_and_header_ranges_have_no_side_effects():
    """两个包都不应出现悬挂comments关系或范围。@return None。"""
    target=Document();a=target.add_paragraph('a').runs[0];b=target.add_paragraph('b').runs[0]
    foreign=Document();other=foreign.add_paragraph('foreign').runs[0]
    header=target.sections[0].header.paragraphs[0].add_run('header')
    before=target._element.xml;foreign_before=foreign._element.xml
    for runs in ([other],[],[b,a],[a,other],[header],[a,a]):
        with unittest.TestCase().assertRaises(ValueError):target.add_comment(runs,'invalid')
        assert target._element.xml==before and foreign._element.xml==foreign_before
    output=BytesIO();target.save(output)
    with ZipFile(output) as archive:assert 'word/comments.xml' not in archive.namelist()

def test_same_document_cross_paragraph_comment_saves_with_consistent_ids():
    """首末边界允许跨段，中间内容自然包含，不要求逐个传run。@return None。"""
    document=Document();first=document.add_paragraph('first').runs[0];last=document.add_paragraph('last').runs[0]
    comment=document.add_comment([first,last],'review',author='Reviewer')
    assert comment.text=='review'
    output=BytesIO();document.save(output);output.seek(0);restored=Document(output)
    assert len(restored.comments)==1 and next(iter(restored.comments)).text=='review'

