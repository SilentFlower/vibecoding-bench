"""通过真实WSGI入口观察Bottle路由、请求协议和模板。"""
from __future__ import annotations

from io import BytesIO, StringIO
import json
import os
from pathlib import Path
import sys
from wsgiref.util import setup_testing_defaults

import bottle
from bottle import Bottle, SimpleTemplate, request


def invoke(app: Bottle, path: str, *, method: str = 'GET', query: str = '',
        body: bytes = b'', content_type: str = '') -> tuple:
    """运行独立合成WSGI请求。@param app 应用。@param path 路径。@param method 方法。@param query 查询。@param body 请求体。@param content_type 类型。@return 状态、头、字节响应。"""
    environment = {}
    setup_testing_defaults(environment)
    environment.update(PATH_INFO=path, REQUEST_METHOD=method, QUERY_STRING=query,
        CONTENT_LENGTH=str(len(body)), CONTENT_TYPE=content_type,
        **{'wsgi.input': BytesIO(body), 'wsgi.errors': StringIO()})
    captured = []

    def start_response(status, headers, exc_info=None):
        """接收真实响应状态。@param status 状态。@param headers 响应头。@param exc_info 异常。@return None。"""
        captured.append((int(status.split()[0]), {key.lower(): value for key, value in headers}))

    iterable = app(environment, start_response)
    try:
        output = b''.join(iterable)
    finally:
        if hasattr(iterable, 'close'):
            iterable.close()
    return (*captured[-1], output)


def routing() -> dict:
    """核路径转换、方法拒绝和HEAD实际调用行为。@return 路由事实。"""
    app, seen = Bottle(), []

    @app.get('/orders/<identifier:int>')
    def order(identifier):
        """返回转换后的标识。@param identifier 整数标识。@return JSON对象。"""
        seen.append(identifier)
        return {'id': identifier}

    get = invoke(app, '/orders/7')
    invalid = invoke(app, '/orders/nope')
    wrong_method = invoke(app, '/orders/7', method='POST')
    head = invoke(app, '/orders/7', method='HEAD')
    return {'typed_route_and_method_checks_are_distinct': get[0] == 200
            and json.loads(get[2]) == {'id': 7} and invalid[0] == 404 and wrong_method[0] == 405,
        'head_uses_get_callback_but_discards_body': head[0] == 200 and head[2] == b''
            and seen == [7, 7] and head[1]['content-length'] == get[1]['content-length']}


def repeated_query() -> dict:
    """核重复查询值保留和标量访问政策。@return 请求事实。"""
    app = Bottle()

    @app.get('/search')
    def search():
        """从实际请求读取筛选。@return JSON对象。"""
        return {'single': request.query['tag'], 'all': request.query.getall('tag'),
            'missing_attribute': request.query.missing, 'missing_get': request.query.get('missing'),
            'bad_number': request.query.get('limit', default=10, type=int)}

    result = invoke(app, '/search', query='tag=A&tag=B&limit=nope')
    return {'query_keeps_repeated_values_while_scalar_access_selects_last': result[0] == 200
        and json.loads(result[2]) == {'single': 'B', 'all': ['A', 'B'],
            'missing_attribute': '', 'missing_get': None, 'bad_number': 10}}


def json_request() -> dict:
    """核JSON解析不等于业务对象校验。@return 实际请求事实。"""
    app = Bottle()

    @app.post('/submit')
    def submit():
        """回显合成解析结果。@return JSON对象。"""
        return {'parsed': request.json}

    mapping = invoke(app, '/submit', method='POST', body=b'{"quantity":0}', content_type='application/json')
    array = invoke(app, '/submit', method='POST', body=b'[1,2]', content_type='application/json')
    malformed = invoke(app, '/submit', method='POST', body=b'{', content_type='application/json')
    wrong_type = invoke(app, '/submit', method='POST', body=b'{"quantity":2}', content_type='text/plain')
    return {'json_parsing_respects_media_type_and_does_not_validate_business_schema':
        mapping[0] == array[0] == wrong_type[0] == 200 and malformed[0] == 400
        and json.loads(mapping[2]) == {'parsed': {'quantity': 0}}
        and json.loads(array[2]) == {'parsed': [1, 2]}
        and json.loads(wrong_type[2]) == {'parsed': None}}


def template_boundary() -> dict:
    """核可信模板中的默认HTML转义和显式原样输出。@return 模板事实。"""
    value = '<b>A&B</b>'
    escaped = SimpleTemplate(source='{{value}}').render(value=value)
    raw = SimpleTemplate(source='{{!value}}').render(value=value)
    return {'simple_template_escapes_values_and_raw_expression_explicitly_bypasses_it':
        escaped == '&lt;b&gt;A&amp;B&lt;/b&gt;' and raw == value}


def application_factory() -> dict:
    """核显式应用实例和逐次请求环境互不混用。@return 应用隔离事实。"""
    first, second = Bottle(), Bottle()

    @first.get('/tenant')
    def tenant():
        """返回本次合成请求值。@return JSON对象。"""
        return {'tenant': request.query.get('name')}

    a = invoke(first, '/tenant', query='name=A')
    b = invoke(first, '/tenant', query='name=B')
    absent = invoke(second, '/tenant', query='name=C')
    return {'explicit_apps_keep_route_registries_separate_and_requests_rebind':
        json.loads(a[2]) == {'tenant': 'A'} and json.loads(b[2]) == {'tenant': 'B'}
        and absent[0] == 404 and len(first.routes) == 1 and not second.routes}


def main() -> None:
    """核单文件候选真实加载并输出精确任务结果。@return None。"""
    entries = {'BT-U01': (routing, 'typed_route_and_method_checks_are_distinct'),
        'BT-C01': (routing, 'head_uses_get_callback_but_discards_body'),
        'BT-U02': (repeated_query, 'query_keeps_repeated_values_while_scalar_access_selects_last'),
        'BT-C02': (json_request, 'json_parsing_respects_media_type_and_does_not_validate_business_schema'),
        'BT-C03': (template_boundary, 'simple_template_escapes_values_and_raw_expression_explicitly_bypasses_it'),
        'BT-P01': (application_factory, 'explicit_apps_keep_route_registries_separate_and_requests_rebind')}
    observe, field = entries[sys.argv[1]]
    root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()
    print(json.dumps({'candidate_import': Path(bottle.__file__).resolve() == root / 'library/bottle.py',
        field: observe()[field]}))


if __name__ == '__main__':
    main()
