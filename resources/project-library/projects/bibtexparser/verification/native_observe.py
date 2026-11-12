"""核文献失败块、已有宏、组织作者、对象归属和写出合同。"""
import json
import os
from pathlib import Path
import sys

import bibtexparser
from bibtexparser import parse_string, write_string
from bibtexparser.middlewares import MergeCoAuthors, SeparateCoAuthors, default_unparse_stack
from bibtexparser.model import DuplicateBlockKeyBlock


def main() -> None:
    """使用v2实际对象，不套用v1字段模型。@return None。"""
    root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()
    result = {'candidate_import': Path(bibtexparser.__file__).resolve() == root / 'library/bibtexparser/__init__.py'}
    task = sys.argv[1]
    if task == 'BT-U01':
        source = '@article{same,title={First}}\n@article{same,title={Second}}'
        library = parse_string(source)
        failure = library.failed_blocks[0]
        result['duplicate_parse_keys_preserve_first_entry_and_explicit_failed_block_evidence'] = (
            len(library.entries) == 1 and library.entries_dict['same']['title'] == 'First'
            and len(library.blocks) == 2 and len(library.failed_blocks) == 1
            and isinstance(failure, DuplicateBlockKeyBlock) and 'Second' in failure.raw
            and failure.ignore_error_block['title'] == '{Second}')
    elif task == 'BT-U02':
        library = parse_string('@string{J={Journal}}\n@article{old,title={Retained}}')
        original = library.entries_dict['old']
        returned = parse_string('@article{new,journal=J,title={Added}}', library=library)
        result['incremental_parse_reuses_existing_macros_without_retransforming_prior_entries'] = (
            returned is library and library.entries_dict['old'] is original
            and original['title'] == 'Retained' and library.entries_dict['new']['journal'] == 'Journal'
            and len(library.strings) == 1 and not library.failed_blocks)
    elif task == 'BT-U03':
        library = parse_string('@article{a,author={Doe, Jane and {Research and Dev}},title={Report}}')
        separated = SeparateCoAuthors(allow_inplace_modification=False).transform(library)
        authors = separated.entries_dict['a']['author']
        merged = MergeCoAuthors(allow_inplace_modification=False).transform(separated)
        result['existing_author_middleware_preserves_braced_organization_and_copy_policy'] = (
            authors == ['Doe, Jane', '{Research and Dev}']
            and merged.entries_dict['a']['author'] == 'Doe, Jane and {Research and Dev}'
            and library.entries_dict['a']['author'] == 'Doe, Jane and {Research and Dev}'
            and separated is not library)
    elif task == 'BT-C01':
        library = parse_string('@article{a,title={Original}}')
        exported = library.entries_dict
        node = exported['a']
        exported.clear()
        retained = 'a' in library.entries_dict
        node['title'] = 'Changed'
        result['entry_index_mapping_is_copied_but_entry_and_field_objects_remain_shared'] = (
            retained and library.entries_dict['a'] is node and library.entries_dict['a']['title'] == 'Changed')
    elif task == 'BT-C02':
        library = parse_string('@article{a,title={Original}}')
        ordinary = write_string(library)
        intact = library.entries_dict['a']['title'] == 'Original'
        inplace = write_string(library, unparse_stack=default_unparse_stack(allow_inplace_modification=True))
        result['default_writing_preserves_input_while_explicit_all_inplace_stack_mutates_representation'] = (
            intact and '{Original}' in ordinary and ordinary == inplace
            and library.entries_dict['a']['title'] == '{Original}')
    elif task == 'BT-P01':
        source = '@proceedings{p,title={Volume}}\n@inproceedings{c,crossref={p},author={Doe, Jane}}'
        library = parse_string(source)
        child = library.entries_dict['c']
        reloaded = parse_string(write_string(library))
        result['crossref_is_retained_without_automatic_parent_field_inheritance'] = (
            child['crossref'] == 'p' and child.get('title') is None
            and library.entries_dict['p']['title'] == 'Volume'
            and reloaded.entries_dict['c'].get('title') is None and not library.failed_blocks)
    else:
        raise ValueError('未冻结的业务任务')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
