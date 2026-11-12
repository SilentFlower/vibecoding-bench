"Public regression tests for PETL-01-DEV; the complete business contract is in materials/PETL-01-DEV-contract.md."
import petl

def test_duplicate_header_single_and_multiple_sources():
    "Verify duplicate header single and multiple sources."
    first=[['x','x'],[1,2]];second=[['x','y','x','x'],[3,4,5,6]]
    assert list(petl.cat(first))==[('x','x'),(1,1)]
    assert list(petl.cat(first,duplicate_fields="occurrence"))==[('x','x'),(1,2)]
    assert list(petl.cat(first,second,duplicate_fields="occurrence"))==[('x','x','y','x'),(1,2,None,None),(3,5,4,6)]

def test_explicit_header_short_row_missing_and_empty_source():
    "Verify explicit header short row missing and empty source."
    table=[['b','a','a'],[7,8],[9,10,11]]
    assert list(petl.cat([],table,duplicate_fields='occurrence',header=['a','a','b'],missing='?'))==[('a','a','b'),(8,'?',7),(10,11,9)]

