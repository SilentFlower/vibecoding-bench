"Public regression tests for TB-PARAGRAPHS-DEV; the complete business contract is in materials/TB-PARAGRAPHS-DEV-contract.md."
from tabulate import tabulate,_wrap_text_to_colwidths

def test_internal_blank_paragraphs_are_preserved():
    assert _wrap_text_to_colwidths([['one\n\ntwo']],[10],numparses=[False])==[['one\n\ntwo']]

def test_leading_blank_and_long_paragraph_wrapping_are_preserved():
    result=_wrap_text_to_colwidths([['\none two\n\nlast']],[4],numparses=[False])[0][0]
    assert result=='\none\ntwo\n\nlast'

def test_blank_cells_stay_blank_and_numbers_keep_bypass():
    assert _wrap_text_to_colwidths([['',12345]],[2,2])==[['',12345]]

def test_grid_render_retains_extra_physical_row_for_empty_paragraph():
    with_blank=tabulate([['one\n\ntwo']],tablefmt='grid',maxcolwidths=[8],disable_numparse=True)
    compact=tabulate([['one\ntwo']],tablefmt='grid',maxcolwidths=[8],disable_numparse=True)
    assert len(with_blank.splitlines())==len(compact.splitlines())+1
