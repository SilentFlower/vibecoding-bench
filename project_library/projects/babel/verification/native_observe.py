"""核金额精度、区域输入、数字符号、时区及翻译发布守卫。"""
import json
import os
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from gettext import GNUTranslations
from io import BytesIO
from pathlib import Path
import sys

import babel
from babel.dates import format_datetime
from babel.messages.catalog import Catalog
from babel.messages.mofile import write_mo
from babel.numbers import NumberFormatError, format_currency, format_decimal, parse_decimal


def main() -> None:
    """仅对固定本地CLDR和合成翻译做独立观察。@return None。"""
    root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()
    result = {'candidate_import': Path(babel.__file__).resolve() == root / 'library/babel/__init__.py'}
    task = sys.argv[1]
    if task == 'BA-U01':
        value = Decimal('1099.98')
        result['currency_digits_and_quantization_are_explicit_display_policies'] = (
            format_currency(value, 'JPY', locale='en_US') == '¥1,100'
            and format_currency(value, 'JPY', locale='en_US', currency_digits=False) == '¥1,099.98'
            and format_decimal(Decimal('1.2346'), locale='en_US') == '1.235'
            and format_decimal(Decimal('1.2346'), locale='en_US', decimal_quantization=False) == '1.2346'
            and value == Decimal('1099.98'))
    elif task == 'BA-U02':
        suggestions = None
        try:
            parse_decimal('30.00', locale='de', strict=True)
        except NumberFormatError as error:
            suggestions = error.suggestions
        result['strict_locale_parsing_reports_suggestions_without_selecting_intent'] = (
            parse_decimal('30.00', locale='de') == Decimal('3000')
            and suggestions == ['3.000', '30']
            and parse_decimal('1.099,98', locale='de', strict=True) == Decimal('1099.98'))
    elif task == 'BA-C01':
        rendered = format_decimal(Decimal('1099.98'), locale='ar_EG', numbering_system='default')
        result['numbering_system_selects_symbols_without_replacing_digit_glyphs'] = (
            rendered == '1٬099٫98'
            and format_decimal(Decimal('1099.98'), locale='ar_EG', numbering_system='latn') == '1,099.98'
            and parse_decimal(rendered, locale='ar_EG', numbering_system='default') == Decimal('1099.98'))
    elif task == 'BA-C02':
        naive = datetime(2026, 1, 2, 10, 0)
        zone = timezone(timedelta(hours=2))
        aware = naive.replace(tzinfo=zone)
        result['naive_datetime_is_assumed_utc_before_explicit_display_conversion'] = (
            format_datetime(naive, 'yyyy-MM-dd HH:mm', tzinfo=zone, locale='en_US') == '2026-01-02 12:00'
            and format_datetime(aware, 'yyyy-MM-dd HH:mm', tzinfo=zone, locale='en_US') == '2026-01-02 10:00'
            and naive.tzinfo is None)
    elif task == 'BA-P01':
        catalog = Catalog(locale='de', creation_date=datetime(2026, 1, 1, tzinfo=timezone.utc))
        catalog.add('Hello %(name)s', 'Hallo %(other)s', flags=['python-format'])
        catalog.add('Review', 'Prüfen', flags=['fuzzy'])
        errors = list(catalog.check())
        ordinary, include_fuzzy = BytesIO(), BytesIO()
        write_mo(ordinary, catalog)
        write_mo(include_fuzzy, catalog, use_fuzzy=True)
        ordinary.seek(0)
        include_fuzzy.seek(0)
        first, second = GNUTranslations(ordinary), GNUTranslations(include_fuzzy)
        result['catalog_validation_is_separate_from_compilation_and_fuzzy_release_policy'] = (
            len(errors) == 1 and errors[0][0].id == 'Hello %(name)s' and len(errors[0][1]) > 0
            and first.gettext('Hello %(name)s') == 'Hallo %(other)s'
            and first.gettext('Review') == 'Review' and second.gettext('Review') == 'Prüfen')
    else:
        raise ValueError('未冻结的业务任务')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
