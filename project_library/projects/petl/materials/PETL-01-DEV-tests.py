"""重复列按名字与第n次出现配对，不丢后续值。"""
import petl

def test_duplicate_header_single_and_multiple_sources():
    """一个表也必须保留两个不同值，联合头保最大重复次数。@return None。"""
    first=[['x','x'],[1,2]];second=[['x','y','x','x'],[3,4,5,6]]
    assert list(petl.cat(first))==[('x','x'),(1,1)]
    assert list(petl.cat(first,duplicate_fields="occurrence"))==[('x','x'),(1,2)]
    assert list(petl.cat(first,second,duplicate_fields="occurrence"))==[('x','x','y','x'),(1,2,None,None),(3,5,4,6)]

def test_explicit_header_short_row_missing_and_empty_source():
    """显式重复输出与短行按相同出现次序映射。@return None。"""
    table=[['b','a','a'],[7,8],[9,10,11]]
    assert list(petl.cat([],table,duplicate_fields='occurrence',header=['a','a','b'],missing='?'))==[('a','a','b'),(8,'?',7),(10,11,9)]

