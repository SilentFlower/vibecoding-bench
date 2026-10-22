"""核结构化日志上下文、选项、惰性调用与受控异步收尾。"""
from asyncio import Event, run
from io import StringIO
from json import dumps
from os import environ
from pathlib import Path
from sys import argv

import loguru
from loguru import logger


def main() -> None:
    """所有sink均为本进程合成目标，退出清理，不接外部日志服务。@return None。"""
    root = Path(environ['PROJECT_CANDIDATE_ROOT']).resolve()
    result = {'candidate_import': Path(loguru.__file__).resolve() == root / 'library/loguru/__init__.py'}
    logger.remove()
    records = []

    def sink(message) -> None:
        """保存实际日志记录快照。@param message 原生日志消息。@return None。"""
        records.append({'message': message.record['message'], 'extra': dict(message.record['extra'])})

    try:
        task = argv[1]
        if task == 'LG-U01':
            logger.add(sink, format='{message}', catch=False)
            logger.configure(extra={'origin': 'global', 'stable': 'global'})
            bound = logger.bind(origin='bound', bound_only='yes')
            with logger.contextualize(origin='context', request='A'):
                bound.info('inside', origin='call')
                logger.info('context')
            logger.info('outside')
            result['record_extra_precedence_and_context_exit_are_distinct'] = (
                records == [
                    {'message': 'inside', 'extra': {'origin': 'call', 'stable': 'global', 'request': 'A', 'bound_only': 'yes'}},
                    {'message': 'context', 'extra': {'origin': 'context', 'stable': 'global', 'request': 'A'}},
                    {'message': 'outside', 'extra': {'origin': 'global', 'stable': 'global'}}])
        elif task == 'LG-U02':
            calls = []

            def expensive() -> str:
                """用明确副作用代替性能计时承诺。@return 合成值。"""
                calls.append('called')
                return 'value'

            logger.add(sink, level='INFO', filter=lambda record: False, catch=False)
            logger.opt(lazy=True).debug('debug {item}', item=expensive)
            before = len(calls)
            logger.opt(lazy=True).info('info {item}', item=expensive)
            result['lazy_values_skip_global_level_but_run_before_sink_filters'] = (
                before == 0 and calls == ['called'] and records == [])
        elif task == 'LG-C01':
            logger.add(sink, format='{message}', catch=False)
            base = logger.opt(capture=False)
            base.info('first', attribute='synthetic')
            base.opt(raw=True).info('second', attribute='synthetic')
            logger.opt(raw=True, capture=False).info('third', attribute='synthetic')
            result['opt_calls_replace_options_instead_of_merging_previous_values'] = (
                records[0]['extra'] == {} and records[1]['extra'] == {'attribute': 'synthetic'}
                and records[2]['extra'] == {})
        elif task == 'LG-C02':
            logger.add(sink, format='{message}', diagnose=False, backtrace=False, catch=False)

            def failing() -> None:
                """仅抛出固定业务异常。@return 不正常返回。"""
                raise ValueError('synthetic rejection')

            default_result = logger.catch(failing)()
            explicit_result = logger.catch(default='rejected')(failing)()
            propagated = False
            try:
                logger.catch(reraise=True)(failing)()
            except ValueError:
                propagated = True
            result['catch_logging_does_not_by_itself_preserve_failure_signaling'] = (
                default_result is None and explicit_result == 'rejected' and propagated and len(records) == 3)
        elif task == 'LG-P01':
            async def observe() -> bool:
                """用实际事件门禁核异步sink的收尾时点。@return 完整性。"""
                entered, release = Event(), Event()
                completed = []

                async def asynchronous(message) -> None:
                    """等待受控放行再完成写入。@param message 实际日志。@return None。"""
                    entered.set()
                    await release.wait()
                    completed.append(message.record['message'])

                handler = logger.add(asynchronous, catch=False)
                logger.info('pending')
                completion = logger.complete()
                await entered.wait()
                before = completed == []
                release.set()
                await completion
                logger.remove(handler)
                return before and completed == ['pending']

            result['async_sink_completion_requires_awaiting_in_the_owning_loop'] = run(observe())
        elif task == 'LG-D01':
            old, first, second = StringIO(), StringIO(), StringIO()
            old_handler = logger.add(old, format='{message}', catch=False)
            error = None
            try:
                logger.configure(handlers=[{'sink': first, 'format': '{message}', 'catch': False},
                    {'sink': second, 'level': 'NOT_A_REAL_LEVEL'}])
            except ValueError as failure:
                error = type(failure).__name__
            logger.info('after failed replacement')
            old_missing = False
            try:
                logger.remove(old_handler)
            except ValueError:
                old_missing = True
            result.update(error=error, old_sink=old.getvalue(), first_sink=first.getvalue(),
                second_sink=second.getvalue(), old_handler_missing=old_missing)
        else:
            raise ValueError('未冻结的业务任务')
    finally:
        logger.remove()
    print(dumps(result))


if __name__ == '__main__':
    main()
