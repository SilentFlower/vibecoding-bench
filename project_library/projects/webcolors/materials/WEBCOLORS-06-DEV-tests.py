"""品牌色板持有自己的数据，不修改内建名称。"""
import unittest
import webcolors
from webcolors.palette import Palette


def test_copied_case_normalized_aliases_and_roundtrip():
    """来源及导出副本随后变化不影响色板。@return None。"""
    source={'Primary':'#369','accent':'#336699'}
    palette=Palette(source);source['Primary']='#000'
    assert palette['PRIMARY']=='#336699' and palette.rgb('primary')==(51,102,153)
    assert palette.aliases('#369')==('accent','primary')
    exported=palette.to_dict();exported['primary']='#000'
    assert Palette(palette.to_dict()).to_dict()==palette.to_dict()
    assert palette['primary']=='#336699'
    with unittest.TestCase().assertRaises(ValueError):webcolors.name_to_hex('primary')


def test_conflict_policies_and_invalid_input():
    """品牌和内建冲突必须选择政策，非法数据拒绝。@return None。"""
    with unittest.TestCase().assertRaises(ValueError):Palette({'red':'#000'},base_spec=webcolors.CSS3)
    assert Palette({'red':'#000'},base_spec=webcolors.CSS3,conflict='brand')['red']=='#000000'
    assert Palette({'red':'#000'},base_spec=webcolors.CSS3,conflict='builtin')['red']=='#ff0000'
    for source in ({'X':'#000','x':'#fff'},{' leading':'#fff'},{'x':'#oops'}):
        with unittest.TestCase().assertRaises(ValueError):Palette(source)

