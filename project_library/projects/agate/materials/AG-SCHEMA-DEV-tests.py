"""公开表级数据质量回归。"""
import agate
import pytest

def table():
    return agate.Table([('A', 2, 'USD'), ('A', -1, 'XXX'), (None, 5, 'USD')],
        ['id', 'amount', 'currency'], [agate.Text(), agate.Number(), agate.Text()])

def test_rules_return_deterministic_structured_positions():
    schema = agate.Schema({'id': {'nullable': False, 'unique': True}, 'amount': {'min': 0}, 'currency': {'choices': ['USD', 'EUR']}})
    assert schema.validate(table()) == [{'row': 1, 'column': 'id', 'code': 'unique'}, {'row': 1, 'column': 'amount', 'code': 'min'},
        {'row': 1, 'column': 'currency', 'code': 'choice'}, {'row': 2, 'column': 'id', 'code': 'null'}]

def test_strict_mode_keeps_structured_errors():
    with pytest.raises(agate.SchemaValidationError) as error:
        agate.Schema({'amount': {'min': 0}}).validate(table(), strict=True)
    assert error.value.errors == ({'row': 1, 'column': 'amount', 'code': 'min'},)

def test_error_limit_is_exact_and_invalid_limits_are_rejected():
    schema = agate.Schema({'id': {'nullable': False, 'unique': True}})
    assert len(schema.validate(table(), max_errors=1)) == 1
    for limit in (0, -1, True, 1.5):
        with pytest.raises(ValueError):
            schema.validate(table(), max_errors=limit)

def test_caller_configuration_and_original_table_are_not_modified():
    rules = {'currency': {'choices': ['USD']}}
    schema = agate.Schema(rules)
    rules['currency']['choices'].append('XXX')
    source = table()
    assert schema.validate(source) == [{'row': 1, 'column': 'currency', 'code': 'choice'}]
    assert source.rows[1]['currency'] == 'XXX'

def test_missing_columns_and_bad_rules_fail_explicitly():
    with pytest.raises(KeyError):
        agate.Schema({'missing': {}}).validate(table())
    for rules in ({'amount': {'unknown': 1}}, {'amount': {'min': 5, 'max': 1}}):
        with pytest.raises(ValueError):
            agate.Schema(rules)

def test_empty_tables_and_nullable_unique_values():
    empty = agate.Table([], ['id'], [agate.Text()])
    assert agate.Schema({'id': {'unique': True}}).validate(empty) == []
    source = agate.Table([(None,), (None,)], ['id'], [agate.Text()])
    assert agate.Schema({'id': {'unique': True}}).validate(source) == []
