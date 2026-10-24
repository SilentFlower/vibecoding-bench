"Public regression tests for TB-PAGES-DEV; the complete business contract is in materials/TB-PAGES-DEV-contract.md."
import pytest
from tabulate import tabulate,SEPARATING_LINE
from tabulate.pages import iter_pages

def test_page_consumption_is_bounded_and_headers_repeat():
    consumed=[]
    def rows():
        for value in range(5):
            consumed.append(value)
            yield [value]
    pages=iter_pages(rows(),2,headers=['n'],tablefmt='plain')
    first=next(pages)
    assert consumed==[0,1] and 'n' in first
    rest=list(pages)
    assert len(rest)==2 and all('n' in page for page in rest)

def test_firstrow_headers_are_not_repeated_as_data():
    pages=list(iter_pages(iter([['name'],['a'],['b']]),1,headers='firstrow',tablefmt='plain'))
    assert len(pages)==2 and 'a' in pages[0] and 'b' in pages[1]

def test_separators_do_not_consume_business_page_size_or_indices():
    rows=[['a'],SEPARATING_LINE,['b'],['c']]
    pages=list(iter_pages(rows,2,headers=['value'],showindex=True,tablefmt='plain'))
    assert pages[0]==tabulate(rows[:3],headers=['value'],showindex=range(2),tablefmt='plain')
    assert pages[1]==tabulate([['c']],headers=['value'],showindex=range(2,3),tablefmt='plain')

def test_invalid_size_empty_input_and_no_empty_final_page():
    with pytest.raises(ValueError):
        list(iter_pages([[1]],True))
    assert list(iter_pages([],2))==[] and len(list(iter_pages([[1],[2]],2)))==1
