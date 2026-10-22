"""核编辑、词袋、截断和归一化分数的业务含义。"""
from json import dumps
from os import environ
from pathlib import Path
from sys import argv

import textdistance
from textdistance import DamerauLevenshtein, Hamming, Jaccard, Levenshtein, words_combinations


def main() -> None:
    """显式关闭业务加速后端以核本次实际候选路径；完整原生另含全部外部库。@return None。"""
    root = Path(environ['PROJECT_CANDIDATE_ROOT']).resolve()
    result = {'candidate_import': Path(textdistance.__file__).resolve() == root / 'library/textdistance/__init__.py'}
    task = argv[1]
    if task == 'TD-U01':
        result['transposition_cost_depends_on_the_selected_edit_model'] = (
            Levenshtein(external=False)('guide', 'guied') == 2
            and DamerauLevenshtein(external=False)('guide', 'guied') == 1)
    elif task == 'TD-U02':
        algorithm = Levenshtein(external=False)
        result['raw_distance_and_normalized_similarity_have_different_scales'] = (
            algorithm('ab', 'abc') == algorithm('ab', 'ac') == 1
            and abs(algorithm.normalized_similarity('ab', 'abc') - 2 / 3) < 1e-12
            and algorithm.normalized_similarity('ab', 'ac') == 0.5)
    elif task == 'TD-C01':
        bag = Jaccard(qval=None, external=False)
        unique = Jaccard(qval=None, as_set=True, external=False)
        result['word_bag_multiplicity_and_set_semantics_are_explicit_choices'] = (
            abs(bag('tea tea book', 'tea book') - 2 / 3) < 1e-12
            and unique('tea tea book', 'tea book') == 1
            and bag('tea book', 'book tea') == 1)
    elif task == 'TD-C02':
        normal, truncate = Hamming(external=False), Hamming(truncate=True, external=False)
        result['truncated_hamming_can_ignore_a_suffix_and_is_not_edit_alignment'] = (
            normal('ab', 'abc') == 1 and truncate('ab', 'abc') == 0
            and normal('ab', 'xab') == 3 and Levenshtein(external=False)('ab', 'xab') == 1)
    elif task == 'TD-P01':
        algorithm = Levenshtein(external=False)
        result['one_edit_normalization_depends_on_length_and_is_not_match_probability'] = (
            algorithm('a', 'b') == algorithm('abcdefghij', 'abcdefghik') == 1
            and algorithm.normalized_similarity('a', 'b') == 0
            and algorithm.normalized_similarity('abcdefghij', 'abcdefghik') == 0.9)
    elif task == 'TD-D01':
        failure = None
        try:
            words_combinations(Levenshtein(external=False), 'tea book', 'book tea')
        except AttributeError as error:
            failure = str(error)
        result.update(error=failure)
    else:
        raise ValueError('未冻结的业务任务')
    print(dumps(result))


if __name__ == '__main__':
    main()
