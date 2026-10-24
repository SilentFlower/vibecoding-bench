"Public regression tests for TEXTDISTANCE-02-DEV; the complete business contract is in materials/TEXTDISTANCE-02-DEV-contract.md."
import textdistance


def test_word_and_qgram_result_and_normalized_units():
    "Verify word and qgram result and normalized units."
    for cls in (textdistance.LCSSeq,textdistance.LCSStr):
        assert cls(qval=None,external=False)('alpha beta gamma','other beta gamma')==['beta','gamma']
        assert cls(qval=2,external=False)('abcd','xbcdy')==[('b','c'),('c','d')]
        assert cls(qval=2,external=False)('a','abc')==[]
        assert cls(qval=None,external=False).normalized_similarity('one two','one three')==0.5


def test_long_path_and_unhashable_tokens():
    "Verify long path and unhashable tokens."
    for cls in (textdistance.LCSSeq,textdistance.LCSStr):
        assert cls(qval=2,external=False)('x'*205+'ab','zab')==[('a','b')]
        assert cls(external=False)([[1],[2],[3]],[[0],[2],[3]])==[[2],[3]]
        assert cls(external=False)((1,2,3),(0,2,3))==(2,3)
    same=lambda *values:len({value.casefold() for value in values})==1
    assert textdistance.LCSSeq(qval=None,test_func=same,external=False)('Alpha beta','alpha BETA')==['Alpha','beta']

