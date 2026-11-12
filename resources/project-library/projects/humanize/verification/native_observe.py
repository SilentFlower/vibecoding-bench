"""核展示单位、时态、数字格式及协程共享的实际业务行为。"""
import asyncio
from datetime import datetime, timedelta
from json import dumps
from os import environ
from pathlib import Path
from sys import argv

import humanize
from humanize import i18n


def main() -> None:
    """逐任务核实际候选源码；不把展示文本当机器数据。@return None。"""
    root = Path(environ['PROJECT_CANDIDATE_ROOT']).resolve()
    result = {'candidate_import': Path(humanize.__file__).resolve() == root / 'library/src/humanize/__init__.py'}
    task = argv[1]
    i18n.deactivate()
    if task == 'HU-U01':
        result['decimal_binary_and_gnu_units_are_distinct'] = [
            humanize.naturalsize(1000), humanize.naturalsize(1000, binary=True),
            humanize.naturalsize(1024, binary=True), humanize.naturalsize(1024, gnu=True)
        ] == ['1.0 kB', '1000 Bytes', '1.0 KiB', '1.0K']
    elif task == 'HU-U02':
        result['duration_display_discards_sign_and_can_suppress_units'] = (
            humanize.precisedelta(-90) == humanize.precisedelta(90) == '1 minute and 30 seconds'
            and humanize.precisedelta(timedelta(hours=49, seconds=33.12), suppress=['days']) == '49 hours and 33.12 seconds'
            and humanize.precisedelta(.1, minimum_unit='minutes') == '0 minutes')
    elif task == 'HU-U03':
        reference = datetime(2026, 1, 1, 12)
        result['tense_depends_on_the_input_type_and_fixed_reference'] = [
            humanize.naturaltime(60, future=True, when=reference),
            humanize.naturaltime(timedelta(seconds=60), future=True, when=reference),
            humanize.naturaltime(reference + timedelta(seconds=60), when=reference)
        ] == ['a minute from now', 'a minute ago', 'a minute from now']
    elif task == 'HU-C01':
        i18n.activate('de_DE')
        outputs = [humanize.intcomma(1234.5, 2), humanize.intcomma('1.234,50', 2)]
        i18n.deactivate()
        result['localized_text_formatting_is_not_input_validation'] = (
            outputs == ['1.234,50', '1.234,50']
            and humanize.intcomma('not a number') == 'not a number')
    elif task == 'HU-C02':
        result['rounded_display_is_lossy_and_not_a_storage_quantity'] = (
            humanize.naturalsize(999999) == humanize.naturalsize(1000000) == '1.0 MB'
            and humanize.naturalsize(.9) == '0 Bytes')
    elif task == 'HU-P01':
        async def controls() -> list[str]:
            """用事件明确切换次序，避免把时间延迟当隔离证据。@return 两协程实际分隔符。"""
            ready, switched = asyncio.Event(), asyncio.Event()

            async def first() -> str:
                """激活德语并等待另一协程停用。@return 等待后的分隔符。"""
                i18n.activate('de_DE')
                ready.set()
                await switched.wait()
                return i18n.decimal_separator()

            async def second() -> str:
                """在同线程的另一协程停用翻译。@return 停用后的分隔符。"""
                await ready.wait()
                i18n.deactivate()
                switched.set()
                return i18n.decimal_separator()

            return await asyncio.gather(first(), second())

        result['thread_local_translation_state_is_shared_between_async_tasks'] = asyncio.run(controls()) == ['.', '.']
    elif task == 'HU-D01':
        first = i18n.activate('de_DE')
        result['cached_translation_reused'] = i18n.activate('de_DE', '/no-such-catalog') is first
    else:
        raise ValueError('未冻结的业务任务')
    i18n.deactivate()
    print(dumps(result))


if __name__ == '__main__':
    main()
