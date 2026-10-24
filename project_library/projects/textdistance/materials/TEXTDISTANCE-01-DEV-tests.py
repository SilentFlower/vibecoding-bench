"Public regression tests for TEXTDISTANCE-01-DEV; the complete business contract is in materials/TEXTDISTANCE-01-DEV-contract.md."
import textdistance


def test_pair_and_multi_sequence_keep_first_spelling():
    "Verify pair and multi sequence keep first spelling."
    same=lambda *chars:len({char.casefold() for char in chars})==1
    algorithm=textdistance.LCSSeq(test_func=same,external=False)
    assert algorithm('AbC','aBc')=='AbC'
    assert algorithm('AbC','aBc','ABC')=='AbC'
    assert algorithm.similarity('A','a')==1


def test_nontransitive_predicate_is_not_replaced_by_hash_key():
    "Verify nontransitive predicate is not replaced by hash key."
    algorithm=textdistance.LCSSeq(test_func=lambda a,b:abs(ord(a)-ord(b))<=1,external=False)
    assert algorithm('ab','bc')=='ab'
    assert algorithm('a','c')==''
    assert textdistance.LCSSeq(external=False)('DIXON','DICKSONX')=='DION'

