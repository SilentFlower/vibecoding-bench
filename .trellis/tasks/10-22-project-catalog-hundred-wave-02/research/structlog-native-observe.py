"""以真实捕获logger和JSON结果核上下文、序列化及测试边界。"""
from decimal import Decimal
import json
import os
from pathlib import Path
import sys

import structlog
from structlog._generic import BoundLogger
from structlog.contextvars import bind_contextvars, clear_contextvars, merge_contextvars
from structlog.processors import JSONRenderer
from structlog.testing import CapturingLogger, capture_logs


def main() -> None:
    """只记录合成日志，不连接远程日志服务。@return None。"""
    root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()
    result = {'candidate_import': Path(structlog.__file__).resolve() == root / 'library/src/structlog/__init__.py'}
    task = sys.argv[1]
    structlog.reset_defaults()
    clear_contextvars()
    try:
        if task == 'SL-U01':
            sink = CapturingLogger()
            payload = {'tags': []}
            base = structlog.wrap_logger(sink, processors=[], wrapper_class=BoundLogger,
                context_class=dict).bind(batch='base', payload=payload)
            child = base.bind(component='settle')
            child.info('done', batch='call', quantity=2)
            payload['tags'].append('LOCAL')
            result['binding_copies_context_shallowly_and_call_values_override_without_rebinding'] = (
                sink.calls[0].kwargs['batch'] == 'call' and sink.calls[0].kwargs['event'] == 'done'
                and structlog.get_context(base)['batch'] == structlog.get_context(child)['batch'] == 'base'
                and 'component' not in structlog.get_context(base)
                and structlog.get_context(child)['component'] == 'settle'
                and structlog.get_context(base) is not structlog.get_context(child)
                and structlog.get_context(base)['payload'] is structlog.get_context(child)['payload'] is payload
                and sink.calls[0].kwargs['payload']['tags'] == ['LOCAL'])
        elif task == 'SL-C01':
            sink = CapturingLogger()
            bind_contextvars(trace='global', region='context')
            logger = structlog.wrap_logger(sink, processors=[merge_contextvars], wrapper_class=BoundLogger,
                context_class=dict).bind(trace='bound')
            logger.info('one')
            logger.info('two', trace='call')
            clear_contextvars()
            logger.info('three')
            result['contextvars_merge_fills_missing_keys_without_overriding_bound_or_call_values'] = (
                sink.calls[0].kwargs['trace'] == 'bound' and sink.calls[0].kwargs['region'] == 'context'
                and sink.calls[1].kwargs['trace'] == 'call' and sink.calls[1].kwargs['region'] == 'context'
                and sink.calls[2].kwargs['trace'] == 'bound' and 'region' not in sink.calls[2].kwargs)
        elif task == 'SL-C02':
            class Order:
                """合成领域值，分别提供结构与字符串表示。"""

                def __structlog__(self):
                    """返回显式领域序列化。@return 保留金额精度的字典。"""
                    return {'amount': '1.20'}

                def __str__(self):
                    """返回可区分的字符串表示。@return 固定合成字面。"""
                    return 'ORDER_LITERAL'

            value = {'order': Order(), 'amount': Decimal('1.20')}
            default = json.loads(JSONRenderer()(None, 'info', value))
            replaced = json.loads(JSONRenderer(default=str)(None, 'info', value))
            result['explicit_json_default_replaces_structlog_fallback_and_currency_policy_is_deliberate'] = (
                default == {'order': {'amount': '1.20'}, 'amount': "Decimal('1.20')"}
                and replaced == {'order': 'ORDER_LITERAL', 'amount': '1.20'})
        elif task == 'SL-U02':
            def redact(logger, method, event):
                """合成业务处理器。@param logger 底层logger。@param method 方法。@param event 事件。@return 脱敏事件。"""
                event['token'] = '[REDACTED]'
                return event

            structlog.configure(processors=[redact], wrapper_class=BoundLogger, context_class=dict)
            logger = structlog.get_logger()
            with capture_logs() as bypassed:
                logger.info('local', token='SYNTHETIC_SECRET')
            with capture_logs(processors=[redact]) as included:
                logger.info('local', token='SYNTHETIC_SECRET')
            result['capture_logs_replaces_configured_processors_unless_explicitly_supplied'] = (
                len(bypassed) == len(included) == 1 and bypassed[0]['token'] == 'SYNTHETIC_SECRET'
                and included[0]['token'] == '[REDACTED]' and structlog.get_config()['processors'] == [redact])
        elif task == 'SL-P01':
            payload = {'nested': {'token': 'SYNTHETIC_SECRET', 'binary': b'x'}}
            decoded = json.loads(JSONRenderer()(None, 'info', payload))
            result['json_rendering_does_not_implicitly_redact_or_recursively_decode_business_values'] = (
                decoded == {'nested': {'token': 'SYNTHETIC_SECRET', 'binary': "b'x'"}}
                and payload['nested']['binary'] == b'x')
        else:
            raise ValueError('未冻结的业务任务')
    finally:
        clear_contextvars()
        structlog.reset_defaults()
    print(json.dumps(result))


if __name__ == '__main__':
    main()
