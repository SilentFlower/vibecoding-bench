"""用真实Flask测试客户端核请求、会话、消息与配置副作用。"""
from datetime import datetime, timezone
from decimal import Decimal
from email.utils import parsedate_to_datetime
import json
import os
from pathlib import Path
import sys
from unittest.mock import patch

import flask
from flask import Flask, flash, g, get_flashed_messages, session


def main() -> None:
    """只运行进程内WSGI客户端，不监听端口或访问外部服务。@return None。"""
    root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()
    result = {'candidate_import': Path(flask.__file__).resolve() == root / 'library/src/flask/__init__.py'}
    app = Flask(__name__, static_folder=None)
    app.config.update(TESTING=True, SECRET_KEY='SYNTHETIC_LOCAL_ONLY')
    task = sys.argv[1]
    if task == 'FL-U01':
        @app.get('/count')
        def count():
            """返回合成会话和局部计数。@return JSON兼容对象。"""
            session['count'] = session.get('count', 0) + 1
            g.seen = getattr(g, 'seen', 0) + 1
            return {'session': session['count'], 'local': g.seen}

        first, other = app.test_client(), app.test_client()
        values = [json.loads(client.get('/count').data) for client in [first, first, other]]
        result['cookie_clients_preserve_session_while_each_standalone_request_gets_fresh_locals'] = (
            values == [{'session': 1, 'local': 1}, {'session': 2, 'local': 1}, {'session': 1, 'local': 1}])
    elif task == 'FL-U02':
        @app.get('/seed')
        def seed():
            """放入完整合成消息。@return 固定响应。"""
            flash('OK', 'success')
            flash('CAUTION', 'warning')
            return 'seeded'

        @app.get('/success')
        def success():
            """只展示成功类别。@return 过滤后消息。"""
            return {'messages': get_flashed_messages(category_filter=['success'])}

        @app.get('/all')
        def all_messages():
            """读取本请求全部消息。@return 完整消息。"""
            return {'messages': get_flashed_messages()}

        @app.get('/both')
        def both():
            """在同请求展示两个类别。@return 分组消息。"""
            return {'success': get_flashed_messages(category_filter=['success']),
                'warning': get_flashed_messages(category_filter=['warning'])}

        client = app.test_client()
        client.get('/seed')
        selected = json.loads(client.get('/success').data)
        after = json.loads(client.get('/all').data)
        client.get('/seed')
        same_request = json.loads(client.get('/both').data)
        result['flash_filtering_does_not_preserve_unshown_categories_for_the_next_request'] = (
            selected == {'messages': ['OK']} and after == {'messages': []}
            and same_request == {'success': ['OK'], 'warning': ['CAUTION']})
    elif task == 'FL-C01':
        instant = datetime(2026, 4, 3, 10, 1, 2, 123456, tzinfo=timezone.utc)
        value = json.loads(app.json.dumps({'created': instant, 'amount': Decimal('1.20')}))
        parsed = parsedate_to_datetime(value['created'])
        result['default_json_dates_use_http_seconds_and_decimals_are_strings'] = (
            parsed == instant.replace(microsecond=0) and parsed != instant
            and value['created'].endswith(' GMT') and value['amount'] == '1.20'
            and isinstance(value['amount'], str))
    elif task == 'FL-C02':
        with patch.dict(os.environ, {'BUSINESS_APP_COUNT': '7', 'BUSINESS_APP_LABEL': '"007"',
                'BUSINESS_APP_FEATURE__ENABLED': 'true', 'BUSINESS_APP_RAW': 'not-json'}, clear=True):
            loaded = app.config.from_prefixed_env(prefix='BUSINESS_APP')
        result['prefixed_env_already_parses_json_and_nested_keys_with_raw_string_fallback'] = (
            loaded is True and app.config['COUNT'] == 7 and type(app.config['COUNT']) is int
            and app.config['LABEL'] == '007' and app.config['FEATURE']['ENABLED'] is True
            and app.config['RAW'] == 'not-json')
    elif task == 'FL-P01':
        before = dict(app.config)
        rejected = False
        with patch.dict(os.environ, {'BUSINESS_APP_A_FIRST': '1', 'BUSINESS_APP_DATABASE': '1',
                'BUSINESS_APP_DATABASE__HOST': '"local"'}, clear=True):
            try:
                app.config.from_prefixed_env(prefix='BUSINESS_APP')
            except TypeError:
                rejected = True
        result['prefixed_env_loading_can_leave_earlier_writes_after_a_nested_type_error'] = (
            rejected and 'A_FIRST' not in before and 'DATABASE' not in before
            and app.config['A_FIRST'] == app.config['DATABASE'] == 1)
    else:
        raise ValueError('未冻结的业务任务')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
