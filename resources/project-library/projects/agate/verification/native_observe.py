"""独立观察Agate类型、派生计算、维表匹配和空值统计。"""
from __future__ import annotations

from decimal import Decimal
from io import StringIO
import json
import os
from pathlib import Path
import sys

import agate
from agate import CastError, Count, Formula, Number, Sum, Table, Text, TypeTester


def input_types() -> dict:
    """核编号、空值策略与采样并非全量保证。@return 类型事实。"""
    raw = 'code,amount,note\n001,2.50,NA\n002,3.75,keep\n'
    inferred = Table.from_csv(StringIO(raw))
    explicit = Table.from_csv(StringIO(raw), column_types={'code': Text(cast_nulls=False),
        'note': Text(cast_nulls=False), 'amount': Number()})
    sample_failure = False
    try:
        Table([('2',), ('oops',)], ['qty'], TypeTester(limit=1))
    except CastError:
        sample_failure = True
    full = Table([('2',), ('oops',)], ['qty'])
    pulls = []

    def rows():
        """记录原构造器实际读取，不把推断样本当流窗口。@return 行迭代器。"""
        for value in ['2', '3', '4']:
            pulls.append(value)
            yield (value,)

    sampled = Table(rows(), ['qty'], TypeTester(limit=1))
    return {'inference_converts_leading_zeroes_and_null_tokens': inferred.rows[0]['code'] == Decimal(1)
            and inferred.rows[0]['note'] is None and inferred.rows[0]['amount'] == Decimal('2.50'),
        'explicit_types_preserve_identifiers_and_literal_null_tokens': explicit.rows[0]['code'] == '001'
            and explicit.rows[0]['note'] == 'NA' and explicit.rows[0]['amount'] == Decimal('2.50'),
        'limited_inference_still_materializes_and_casts_all_rows': sample_failure
            and list(full.columns['qty'].values()) == ['2', 'oops']
            and pulls == ['2', '3', '4'] and len(sampled.rows) == 3}


def derived_tables() -> dict:
    """核派生表和计算依赖的真实输入时点。@return 派生事实。"""
    source = Table([('A', 2), ('B', 1), ('C', 3)], ['order', 'amount'], [Text(), Number()])
    chosen = source.where(lambda row: row['amount'] >= 2).order_by('amount', reverse=True)
    first = Formula(Number(), lambda row: row['amount'] * 2)
    second = Formula(Number(), lambda row: row['double'] + 1)
    simultaneous_rejected = False
    try:
        source.compute([('double', first), ('plus', second)])
    except KeyError:
        simultaneous_rejected = True
    intermediate = source.compute([('double', first)])
    result = intermediate.compute([('plus', second)])
    return {'derivatives_preserve_original_rows_and_order': chosen is not source
            and list(source.columns['order'].values()) == ['A', 'B', 'C']
            and list(chosen.columns['order'].values()) == ['C', 'A']
            and source.column_names == ('order', 'amount'),
        'dependent_computations_require_explicit_stages': simultaneous_rejected
            and list(result.columns['plus'].values()) == [Decimal(5), Decimal(3), Decimal(7)]
            and source.column_names == ('order', 'amount') and intermediate.column_names == ('order', 'amount', 'double')}


def dimension_join() -> dict:
    """核重复匹配和完整匹配检查并非唯一约束。@return 连接事实。"""
    left = Table([('A', 2), ('A', 3), ('B', 1)], ['key', 'qty'], [Text(), Number()])
    right = Table([('A', 'east'), ('A', 'west')], ['key', 'zone'], [Text(), Text()])
    joined = left.join(right, 'key')
    inner = left.join(right, 'key', inner=True)
    missing_rejected = False
    try:
        left.join(right, 'key', require_match=True)
    except ValueError:
        missing_rejected = True
    matched_left = left.where(lambda row: row['key'] == 'A')
    duplicates_accepted = matched_left.join(right, 'key', require_match=True)
    return {'duplicate_dimension_matches_expand_measures': len(joined.rows) == 5
            and joined.aggregate(Sum('qty')) == 11 and left.aggregate(Sum('qty')) == 6
            and len(inner.rows) == 4 and inner.aggregate(Sum('qty')) == 10
            and joined.rows[-1]['zone'] is None,
        'require_match_rejects_missing_not_duplicate_keys': missing_rejected and len(duplicates_accepted.rows) == 4}


def summaries() -> dict:
    """核金额和完整率不能从一个Sum推导。@return 统计事实。"""
    table = Table([('east', 2), ('east', None), ('west', 3)], ['region', 'amount'], [Text(), Number()])
    grouped = table.group_by('region').aggregate([('total', Sum('amount')), ('present', Count('amount')), ('rows', Count())])
    empty = Table([(None,), (None,)], ['amount'], [Number()])
    zero = Table([(0,), (0,)], ['amount'], [Number()])
    return {'group_totals_and_non_null_counts_have_distinct_meanings': table.aggregate(Sum('amount')) == 5
            and table.aggregate(Count()) == 3 and table.aggregate(Count('amount')) == 2
            and table.aggregate(Count('amount', None)) == 1
            and grouped.rows['east']['total'] == 2 and grouped.rows['east']['present'] == 1
            and grouped.rows['east']['rows'] == 2 and grouped.rows['west']['total'] == 3,
        'all_null_sum_does_not_establish_zero_measurements': empty.aggregate(Sum('amount')) == zero.aggregate(Sum('amount')) == 0
            and empty.aggregate(Count('amount')) == 0 and zero.aggregate(Count('amount')) == 2}


def main() -> None:
    """核真实候选并输出本任务断言。@return None。"""
    task = sys.argv[1]
    entries = {'AG-U01': (input_types, ['inference_converts_leading_zeroes_and_null_tokens']),
        'AG-C01': (input_types, ['explicit_types_preserve_identifiers_and_literal_null_tokens']),
        'AG-U02': (input_types, ['limited_inference_still_materializes_and_casts_all_rows']),
        'AG-U03': (derived_tables, ['derivatives_preserve_original_rows_and_order']),
        'AG-C02': (derived_tables, ['dependent_computations_require_explicit_stages']),
        'AG-P01': (dimension_join, ['duplicate_dimension_matches_expand_measures', 'require_match_rejects_missing_not_duplicate_keys']),
        'AG-U04': (summaries, ['group_totals_and_non_null_counts_have_distinct_meanings']),
        'AG-C03': (summaries, ['all_null_sum_does_not_establish_zero_measurements'])}
    observe, fields = entries[task]
    facts = observe()
    root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()
    print(json.dumps({'candidate_import': Path(agate.__file__).resolve() == root / 'library/agate/__init__.py',
        **{field: facts[field] for field in fields}}))


if __name__ == '__main__':
    main()
