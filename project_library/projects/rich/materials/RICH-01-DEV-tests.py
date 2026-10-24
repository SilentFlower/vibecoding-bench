"""裁切测量与字素范围一致，零宽容器不能触发范围或除零错误。"""
from rich.cells import split_graphemes,cell_len,_split_text,set_cell_size,chop_cells
from rich.console import Console
from rich.text import Text


def test_zero_width_and_all_zero_graphemes_have_bounded_behavior():
    """ASCII与非ASCII非正宽度统一为空，不存在零除。@return None。"""
    for value in ('abc','中文','\u200d\u200d','e\u0301'):
        for width in (0,-1,-10):
            assert set_cell_size(value,width)=='' and chop_cells(value,width)==[]
            assert list(Text(value).wrap(Console(),width))==[]
    assert _split_text('\u200d\u200d',1)==('\u200d\u200d','')


def test_special_measurement_and_splits_share_the_same_spans():
    """复杂ZWJ/VS与中文按同一分段宽度测量，不越过最后span。@return None。"""
    for value in ('👩\u200d🔧中文','❤\ufe0f\u200d❤\ufe0fX','\u200dA\ufe0f中'):
        spans,width=split_graphemes(value)
        assert cell_len(value)==width
        assert _split_text(value,width+10)==(value,'')
        for size in range(width+2):assert cell_len(set_cell_size(value,size))==size

