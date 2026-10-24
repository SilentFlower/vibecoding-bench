"Public regression tests for TREELIB-04-DEV; the complete business contract is in materials/TREELIB-04-DEV-contract.md."
import io
import unittest
from treelib.csvio import read_csv,write_csv


def test_out_of_order_unicode_quoted_data_roundtrip():
    "Verify out of order unicode quoted data roundtrip."
    raw='id,parent,tag,data\nchild,root,"含,逗号","{""n"":0}"\nroot,,根,null\nempty,root,,false\n'
    tree=read_csv(io.StringIO(raw));tree['root'].expanded=False
    stream=io.StringIO();write_csv(tree,stream);again=read_csv(io.StringIO(stream.getvalue()))
    assert len(again)==3 and again['child'].tag=='含,逗号' and again['child'].data=={'n':0}
    assert again['empty'].tag=='' and again['empty'].data is False
    assert [node.identifier for node in again.children('root')]==['child','empty']


def test_invalid_columns_and_unreachable_records_reject():
    "Verify invalid columns and unreachable records reject."
    for raw in ('id,parent,tag,data\nr,,Root,null\nx,missing,X,null\n','id,parent,tag,data\nr,,R,null\na,b,A,null\nb,a,B,null\n','id,parent,tag,tag\nr,,a,b\n','id,parent,tag,data\nx,,X,null\nx,x,X,null\n'):
        with unittest.TestCase().assertRaises(ValueError):read_csv(io.StringIO(raw))

