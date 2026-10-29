"""核重复输入、来源优先级、文件流和响应资源归属。"""
import json
import os
from io import BytesIO
from pathlib import Path
import sys

import werkzeug
from werkzeug.datastructures import CombinedMultiDict, FileStorage, MultiDict
from werkzeug.wrappers import Response


def main() -> None:
    """只用本地内存对象验证五项独立业务边界。@return None。"""
    root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()
    result = {'candidate_import': Path(werkzeug.__file__).resolve() == root / 'library/src/werkzeug/__init__.py'}
    task = sys.argv[1]
    if task == 'WZ-U01':
        values = MultiDict([('qty', 'bad'), ('qty', '2'), ('qty', None), ('qty', '3')])
        result['typed_getlist_omits_invalid_items_and_flat_mapping_keeps_first_only'] = (
            values.get('qty', default=99, type=int) == 99 and values.getlist('qty', type=int) == [2, 3]
            and values.to_dict() == {'qty': 'bad'}
            and values.to_dict(flat=False) == {'qty': ['bad', '2', None, '3']})
    elif task == 'WZ-U02':
        values = MultiDict({'qty': ['2', '3']})
        values.update({'qty': ['4']})
        extended = values.getlist('qty')
        first = values.pop('qty')
        values.setlist('qty', ['5', '6'])
        result['update_appends_pop_discards_all_and_setlist_explicitly_replaces'] = (
            extended == ['2', '3', '4'] and first == '2'
            and values.getlist('qty') == ['5', '6']
            and MultiDict({'qty': ['2', '3']}).poplist('qty') == ['2', '3'])
        discarded = MultiDict({'qty': ['2', '3']})
        discarded.pop('qty')
        result['update_appends_pop_discards_all_and_setlist_explicitly_replaces'] &= 'qty' not in discarded
    elif task == 'WZ-C01':
        query, form = MultiDict({'qty': ['bad', '2']}), MultiDict({'qty': '7'})
        combined = CombinedMultiDict([query, form])
        frozen = combined.copy()
        before = combined['qty']
        converted = combined.get('qty', type=int)
        all_values = combined.getlist('qty')
        query.setlist('qty', ['9'])
        result['combined_raw_and_converted_precedence_differ_and_copy_freezes_structure'] = (
            before == 'bad' and converted == 7 and all_values == ['bad', '2', '7']
            and combined['qty'] == '9' and frozen.getlist('qty') == ['bad', '2', '7']
            and isinstance(frozen, MultiDict) and not isinstance(frozen, CombinedMultiDict))
    elif task == 'WZ-C02':
        source, target = BytesIO(b'ABCDEF'), BytesIO()
        upload = FileStorage(stream=source, filename='synthetic.bin')
        source.seek(2)
        upload.save(target)
        active = not source.closed and not target.closed
        source.seek(0)
        complete = BytesIO()
        upload.save(complete)
        upload.close()
        result['file_save_copies_from_current_position_and_keeps_caller_destination_open'] = (
            target.getvalue() == b'CDEF' and complete.getvalue() == b'ABCDEF'
            and active and source.closed and not target.closed and not complete.closed)
        target.close()
        complete.close()
    elif task == 'WZ-P01':
        events = []

        def chunks():
            """记录实际惰性遍历和生成器清理。@return 两段字节。"""
            try:
                events.append('start')
                yield b'A'
                events.append('second')
                yield b'B'
            finally:
                events.append('generator-finally')

        response = Response(chunks())
        response.call_on_close(lambda: events.append('response-close'))
        lazy = events == [] and response.is_streamed
        data = response.get_data()
        after_read = list(events)
        again = response.get_data()
        response.close()
        result['reading_stream_data_eagerly_consumes_and_caches_but_close_hooks_require_close'] = (
            lazy and data == again == b'AB' and not response.is_streamed
            and after_read == ['start', 'second', 'generator-finally']
            and events == ['start', 'second', 'generator-finally', 'response-close'])
    else:
        raise ValueError('未冻结的业务任务')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
