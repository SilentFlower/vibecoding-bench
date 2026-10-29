"""核SQL文本边界、非验证分类、标识别名和本地文件交付。"""
from contextlib import redirect_stderr
from io import StringIO
import json
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory

import sqlparse
from sqlparse import cli, tokens
from sqlparse.lexer import Lexer, tokenize
from sqlparse.sql import Identifier


def main() -> None:
    """只解析文本与合成本地文件，不连接数据库。@return None。"""
    root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()
    result = {'candidate_import': Path(sqlparse.__file__).resolve() == root / 'library/sqlparse/__init__.py'}
    task = sys.argv[1]
    if task == 'SP-U01':
        source = "select 'a;b'; select $$c;d$$;"
        result['statement_splitting_keeps_quoted_semicolons_and_can_remove_delimiters'] = (
            sqlparse.split(source) == ["select 'a;b';", 'select $$c;d$$;']
            and sqlparse.split(source, strip_semicolon=True) == ["select 'a;b'", 'select $$c;d$$'])
    elif task == 'SP-U02':
        parsed = sqlparse.parse('select from')
        result['statement_type_and_successful_formatting_do_not_validate_sql_grammar'] = (
            len(parsed) == 1 and parsed[0].get_type() == 'SELECT'
            and sqlparse.format('select from', keyword_case='upper') == 'SELECT FROM')
    elif task == 'SP-C01':
        statement = sqlparse.parse('SELECT p.name AS display FROM people p;')[0]
        identifiers = [token for token in statement.tokens if isinstance(token, Identifier)]
        result['identifier_display_alias_and_lexical_parent_are_distinct_from_resolved_lineage'] = (
            len(identifiers) == 2 and identifiers[0].get_real_name() == 'name'
            and identifiers[0].get_parent_name() == 'p' and identifiers[0].get_alias() == 'display'
            and identifiers[0].get_name() == 'display'
            and identifiers[1].get_real_name() == 'people' and identifiers[1].get_alias() == 'p')
    elif task == 'SP-C02':
        before = list(tokenize('BUSINESSXYZ'))
        private = Lexer()
        private.default_initialization()
        private.add_keywords({'BUSINESSXYZ': tokens.Keyword})
        local = list(private.get_tokens('BUSINESSXYZ'))
        after = list(tokenize('BUSINESSXYZ'))
        result['private_lexer_keyword_configuration_does_not_reconfigure_default_parser'] = (
            before == after == [(tokens.Name, 'BUSINESSXYZ')]
            and local == [(tokens.Keyword, 'BUSINESSXYZ')])
    elif task == 'SP-P01':
        with TemporaryDirectory() as temporary:
            target = Path(temporary) / 'synthetic.sql'
            original = b'select 1;\n'
            target.write_bytes(original)
            error = StringIO()
            with redirect_stderr(error):
                code = cli.main(['--in-place', '--indent_width', '-1', str(target)])
            result['inplace_destination_is_truncated_before_invalid_formatter_options_are_reported'] = (
                code == 1 and target.read_bytes() == b'' and 'Invalid options' in error.getvalue())
    else:
        raise ValueError('未冻结的业务任务')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
